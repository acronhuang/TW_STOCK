#!/usr/bin/env python3
"""委員模型重播評測：用歷史合議樣本重跑盲投，對照 20 日後的實際超額報酬。

只讀資料庫、只輸出到 logs/committee_replay/，不寫 live 集合。候選模型放在獨立的 Ollama 實例
（--lab-url），現任委員用正式節點；候選名單一律從命令列給，不寫死在程式裡。

  sample   從 team_analysis × verdict_detail 抽樣（日期分層、固定種子）
  run      重播投票（可續跑；遇到夜間分析進程或超過 --until 就停）
  report   彙整各模型與各種 3 人組合的表現
"""
import argparse
import itertools
import json
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from src.analysis import committee_replay as cr  # noqa: E402
from src.moe import consensus, model_nodes  # noqa: E402

OUT = ROOT / "logs" / "committee_replay"
SAMPLES, RESULTS = OUT / "samples.json", OUT / "results.jsonl"
BUSY = "evening_pipeline|team_daily|team_analyze|risk_deliberation"


def cmd_sample(args):
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    details = {}
    for d in db.verdict_detail.find({"window": 20, "date": {"$gte": start, "$lte": end}},
                                    {"_id": 0, "date": 1, "symbol": 1, "excess": 1, "fwd_ret": 1}):
        if d.get("excess") is not None:
            details[(d["date"], d["symbol"])] = d
    latest = {}
    cursor = db.team_analysis.find(
        {"date": {"$gte": start, "$lte": end}, "consensus.votes.0": {"$exists": True}, "advisor": {"$type": "string"}},
        {"_id": 0, "date": 1, "symbol": 1, "name": 1, "advisor": 1, "reports": 1, "consensus": 1, "updated_at": 1},
    ).sort("updated_at", 1)
    for d in cursor:
        key = (d["date"], d["symbol"])
        if key in details and d.get("reports"):
            latest[key] = d
    pool = []
    for key, d in latest.items():
        votes = (d["consensus"].get("votes") or [])
        pool.append({
            "date": key[0].strftime("%Y-%m-%d"), "symbol": key[1], "name": d.get("name", ""),
            "advisor": d["advisor"], "reports": d["reports"],
            "advisor_rating": consensus._advisor_rating(d["advisor"]),
            "live_votes": {v["model"]: v.get("vote") for v in votes},
            "excess": float(details[key]["excess"]), "fwd_ret": details[key].get("fwd_ret"),
        })
    rows = cr.sample_rows(pool, args.n, args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    SAMPLES.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    dates = sorted({r["date"] for r in rows})
    print(f"母體 {len(pool)} 筆 → 抽樣 {len(rows)} 筆，{len(dates)} 個日期（{dates[0]} ~ {dates[-1]}）")


def _load_samples():
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def _done():
    done = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not r.get("err"):
                done.add((r["model"], r["date"], r["symbol"]))
    return done


def _call(url, model, prompt, timeout=150):
    started = time.time()
    body = requests.post(f"{url}/api/generate", timeout=timeout, json={
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 160}}).json()
    if "error" in body:
        raise RuntimeError(body["error"])
    return (body.get("response") or "").strip(), int((time.time() - started) * 1000)


def _worker(url, models, rows, done, lock, handle, deadline):
    for model in models:
        consecutive_errors = 0
        for row in rows:
            if time.time() > deadline:
                return
            if (model, row["date"], row["symbol"]) in done:
                continue
            record = {"model": model, "date": row["date"], "symbol": row["symbol"]}
            try:
                response, ms = _call(url, model, cr.build_prompt(row["symbol"], row["name"], row["advisor"], row["reports"]))
                vote, reason, hollow = cr.parse_vote(response)
                record.update(vote=vote, reason=reason[:80], hollow=hollow, ms=ms)
                consecutive_errors = 0
            except Exception as error:  # noqa: BLE001 - 單筆失敗要記下來而不是中止整批
                record["err"] = str(error)[:120]
                consecutive_errors += 1
            with lock:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            if consecutive_errors >= 5:
                print(f"[{model}] 連續 5 次失敗，略過此模型：{record['err']}", flush=True)
                break


def cmd_prepare(args):
    for model in args.candidates.split(","):
        r = requests.post(f"{args.lab_url}/api/pull", json={"model": model, "stream": False}, timeout=1800).json()
        print(model, r.get("status", r), flush=True)


def cmd_run(args):
    busy = subprocess.run(["pgrep", "-af", BUSY], capture_output=True, text=True).stdout
    if [line for line in busy.splitlines() if "pgrep" not in line] and not args.force:
        print("夜間或分析進程在跑，拒絕執行（保護 live）")
        return 2
    hour, minute = map(int, args.until.split(":"))
    deadline = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
    rows, done, lock = _load_samples(), _done(), threading.Lock()
    groups = {}
    for model in consensus.COMMITTEE:
        groups.setdefault(model_nodes.node_of(model), []).append(model)
    groups[args.lab_url] = [m for m in args.candidates.split(",") if m]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as handle:
        threads = [threading.Thread(target=_worker, args=(url, models, rows, done, lock, handle, deadline))
                   for url, models in groups.items()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    print("完成或已到截止時間；用 report 查看結果")
    return 0


def _pct(x):
    return "  -  " if x is None else f"{x * 100:5.1f}"


def cmd_report(args):
    samples = {(r["date"], r["symbol"]): r for r in _load_samples()}
    votes = {}
    latency = {}
    hollow = {}
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("err"):
            continue
        votes.setdefault(r["model"], {})[(r["date"], r["symbol"])] = r["vote"]
        latency.setdefault(r["model"], []).append(r["ms"])
        hollow.setdefault(r["model"], []).append(r["hollow"])
    for model in consensus.COMMITTEE:  # 現任委員當時 live 實際投的票，當第二個對照
        votes[f"live:{model}"] = {k: s["live_votes"].get(model) for k, s in samples.items()}

    def rows_for(series):
        return [{"date": k[0], "vote": v, "excess": samples[k]["excess"]} for k, v in series.items() if k in samples]

    print(f"樣本 {len(samples)} 筆；超額＝20 交易日後相對同日分析池均值。價差＝買進組均超額 − 賣出組均超額（百分點）。\n")
    print(f"{'模型':30s} {'N':>4s} {'棄權%':>6s} {'空洞%':>6s} {'買%':>5s} {'持%':>5s} {'賣%':>5s} {'秒':>4s} {'買N':>4s} {'賣N':>4s} {'價差pp':>7s} {'95%區間':>16s}")
    for model, series in sorted(votes.items()):
        dist = cr.vote_distribution(list(series.values()))
        stats = cr.outcome_stats(rows_for(series))
        ci = cr.cluster_bootstrap_spread(rows_for(series))
        spread = "  -  " if stats["spread"] is None else f"{stats['spread'] * 100:+6.2f}"
        band = "-" if ci is None else f"[{ci[0] * 100:+.2f}, {ci[1] * 100:+.2f}]"
        secs = f"{sum(latency[model]) / len(latency[model]) / 1000:4.1f}" if model in latency else "   -"
        hol = _pct(sum(hollow[model]) / len(hollow[model])) if model in hollow else "  -  "
        print(f"{model:30s} {len(series):4d} {_pct(dist['abstain']):>6s} {hol:>6s} {_pct(dist['買進']):>5s} {_pct(dist['持有']):>5s} {_pct(dist['賣出']):>5s} {secs:>4s} {stats['n_buy']:4d} {stats['n_sell']:4d} {spread:>7s} {band:>16s}")

    replay = [m for m in votes if not m.startswith("live:")]
    usable = [m for m in replay if cr.vote_distribution(list(votes[m].values()))["abstain"] <= 0.05]
    print("\n同票率矩陣（%，只看雙方都有票的樣本）")
    print(" " * 30 + "".join(f"{i:>5d}" for i in range(len(replay))))
    for i, a in enumerate(replay):
        print(f"{i:2d} {a:27s}" + "".join(f"{_pct(cr.agreement(votes[a], votes[b])[0]):>5s}" for b in replay))

    def committee(combo):
        keys = sorted(set.intersection(*(set(votes[m]) for m in combo)))
        final = {k: cr.final_from_votes([votes[m][k] for m in combo], samples[k]["advisor_rating"]) for k in keys}
        pair = [cr.agreement(votes[a], votes[b])[0] for a, b in itertools.combinations(combo, 2)]
        pair = [p for p in pair if p is not None]
        return final, (sum(pair) / len(pair) if pair else None)

    print("\n三人組合（多數決，平手依顧問草案；可用模型＝棄權 ≤5%）。組合很多，屬探索性結果，勝出者要再用新樣本複驗。")
    base = tuple(consensus.COMMITTEE)
    table = []
    for combo in itertools.combinations(usable, 3):
        final, mean_same = committee(combo)
        stats = cr.outcome_stats(rows_for(final))
        if stats["spread"] is not None:
            table.append((stats["spread"], combo, mean_same, stats, rows_for(final)))
    table.sort(key=lambda t: -t[0])
    shown = table[: args.top]
    base_row = next((t for t in table if set(t[1]) == set(base)), None)
    if base_row and base_row not in shown:
        shown.append(base_row)
    for spread, combo, mean_same, stats, rows in shown:
        ci = cr.cluster_bootstrap_spread(rows)
        band = "-" if ci is None else f"[{ci[0] * 100:+.2f}, {ci[1] * 100:+.2f}]"
        tag = "  ← 現任" if set(combo) == set(base) else ""
        print(f"  價差 {spread * 100:+6.2f}pp {band:>18s}  買N={stats['n_buy']:3d} 賣N={stats['n_sell']:3d}  成員平均同票 {_pct(mean_same)}%  {' + '.join(combo)}{tag}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--start", default="2026-08-21")
    s.add_argument("--end", default="2026-09-11")
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--seed", type=int, default=20261013)
    for name in ("prepare", "run"):
        p = sub.add_parser(name)
        p.add_argument("--candidates", required=True, help="逗號分隔的候選模型")
        p.add_argument("--lab-url", required=True, help="放候選模型的獨立 Ollama 實例")
        if name == "run":
            p.add_argument("--until", default="19:30")
            p.add_argument("--force", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    return {"sample": cmd_sample, "prepare": cmd_prepare, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
