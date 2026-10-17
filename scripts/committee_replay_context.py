#!/usr/bin/env python3
"""委員重播的脈絡實驗：多給「截止當日前 30 天可見的公告」，看合議價差有沒有變好。

同樣的樣本、同樣的三位現任委員、同樣的第一輪盲投提示，只在關鍵數據後面多附公告清單（來源 wiki_raw，
一律以 available_at 篩選，截止時間為分析日 20:00）。對照組直接用既有重播的投票，沒有公告的樣本提示與
對照組完全相同、不重跑。以日期為單位重抽，看「附公告後的價差 − 原價差」的 95% 區間。

  prepare   依 wiki_raw 為每個樣本建好公告脈絡並凍結（ctx_plan.json）
  run       重播有公告的樣本（可續跑；分析流程在跑時拒絕執行，避免拖慢正式機）
  status    還剩幾筆
  report    對照結果
"""
import argparse
import json
import random
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pymongo import MongoClient  # noqa: E402

from scripts import committee_replay as base  # noqa: E402
from src.analysis import committee_replay as cr  # noqa: E402
from src.moe import consensus, model_nodes  # noqa: E402

DIRS = ("logs/committee_replay", "logs/committee_replay_v2")
CUTOFF_HOUR = 20
LOOKBACK_DAYS = 30
MAX_ITEMS = 8
MAX_CHARS = 1800
DAYS = LOOKBACK_DAYS


def one_line(text, limit):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def cutoff_for(day):
    return datetime.fromisoformat(day).replace(hour=CUTOFF_HOUR, minute=0, second=0, microsecond=0)


def earliest_revisions(rows):
    """同一則公告若有更正版，只取最早寫入的那一版，避免用到截止後才知道的更正。"""
    first = {}
    for row in rows:
        key = row.get("nkey") or id(row)
        if key not in first or row["captured_at"] < first[key]["captured_at"]:
            first[key] = row
    return list(first.values())


def build_context(rows, cutoff, days=LOOKBACK_DAYS, max_items=MAX_ITEMS, max_chars=MAX_CHARS):
    """回 (提示用文字, 窗口內公告總數)；窗口內沒有公告回 ("", 0)。"""
    window = [r for r in earliest_revisions(rows) if cutoff - timedelta(days=days) < r["available_at"] <= cutoff]
    window.sort(key=lambda r: r["available_at"], reverse=True)
    if not window:
        return "", 0
    lines, used = [], 0
    for row in window[:max_items]:
        line = f"- {row['available_at']:%Y-%m-%d} {one_line(row['title'], 80)}"
        if row.get("body"):
            line += f"：{one_line(row['body'], 120)}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    header = f"【近 {days} 天公告（截至 {cutoff:%Y-%m-%d}，共 {len(window)} 則，列最近 {len(lines)} 則）】"
    return header + "\n" + "\n".join(lines), len(window)


def treatment_prompt(row, context):
    summary = cr.data_summary(row["reports"] or {}) + (("\n\n" + context) if context else "")
    return consensus._round1_prompt(row["symbol"], row["name"], (row["advisor"] or "")[:1500], summary)


def paired_spread_diff(items, iters=3000, seed=7):
    """items: [{date, base, treat, excess}]；回 (價差差距, 區間下界, 上界, 差距>0 的比例)，以日期為單位重抽。"""
    def spread(sample, key):
        return cr.outcome_stats([{"vote": i[key], "excess": i["excess"]} for i in sample])["spread"]

    point_b, point_t = spread(items, "base"), spread(items, "treat")
    by_date = defaultdict(list)
    for item in items:
        by_date[item["date"]].append(item)
    dates = sorted(by_date)
    if len(dates) < 2 or point_b is None or point_t is None:
        return None
    rng, diffs = random.Random(seed), []
    for _ in range(iters):
        sample = [i for d in (rng.choice(dates) for _ in dates) for i in by_date[d]]
        b, t = spread(sample, "base"), spread(sample, "treat")
        if b is not None and t is not None:
            diffs.append(t - b)
    if not diffs:
        return None
    diffs.sort()
    return point_t - point_b, diffs[int(0.025 * len(diffs))], diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))], sum(d > 0 for d in diffs) / len(diffs)


def load_samples(directory):
    return json.loads((ROOT / directory / "samples.json").read_text(encoding="utf-8"))


def suffix():
    return "" if DAYS == LOOKBACK_DAYS else f"_{DAYS}"


def plan_path(directory):
    return ROOT / directory / f"ctx_plan{suffix()}.json"


def results_path(directory):
    return ROOT / directory / f"ctx_results{suffix()}.jsonl"


def cmd_prepare(args):
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    data_start = db["wiki_raw"].find_one({"kind": "announcement"}, {"available_at": 1}, sort=[("available_at", 1)])["available_at"]
    for directory in DIRS:
        plan, truncated = [], 0
        for row in load_samples(directory):
            cutoff = cutoff_for(row["date"])
            truncated += cutoff - timedelta(days=DAYS) < data_start
            docs = list(db["wiki_raw"].find(
                {"kind": "announcement", "stock_id": row["symbol"], "available_at": {"$gt": cutoff - timedelta(days=DAYS), "$lte": cutoff}},
                {"nkey": 1, "title": 1, "body": 1, "available_at": 1, "captured_at": 1}))
            context, count = build_context(docs, cutoff, days=DAYS)
            plan.append({"date": row["date"], "symbol": row["symbol"], "ctx_n": count, "context": context})
        plan_path(directory).write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        with_ctx = sum(1 for p in plan if p["ctx_n"])
        print(f"{directory}: 窗口 {DAYS} 天；樣本 {len(plan)}；有公告脈絡 {with_ctx}（{with_ctx / max(1, len(plan)):.0%}）；每筆平均 {sum(p['ctx_n'] for p in plan) / max(1, with_ctx):.1f} 則；"
              f"窗口超出資料起點（{data_start:%Y-%m-%d}）而被截短的樣本 {truncated}")


def _done(directory):
    done = set()
    if results_path(directory).exists():
        for line in results_path(directory).read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if not record.get("err"):
                done.add((record["model"], record["date"], record["symbol"]))
    return done


def _todo(directory):
    plan = {(p["date"], p["symbol"]): p for p in json.loads(plan_path(directory).read_text(encoding="utf-8"))}
    samples = {(r["date"], r["symbol"]): r for r in load_samples(directory)}
    return [(samples[k], p["context"]) for k, p in plan.items() if p["ctx_n"]]


def remaining():
    total = 0
    for directory in DIRS:
        done = _done(directory)
        total += sum(1 for row, _ in _todo(directory) for m in consensus.COMMITTEE if (m, row["date"], row["symbol"]) not in done)
    return total


def _worker(url, models, items, done, lock, handle, deadline):
    for model in models:
        errors = 0
        for row, context in items:
            if time.time() > deadline:
                return
            if (model, row["date"], row["symbol"]) in done:
                continue
            record = {"model": model, "date": row["date"], "symbol": row["symbol"]}
            try:
                response, ms = base._call(url, model, treatment_prompt(row, context))
                vote, reason, hollow = cr.parse_vote(response)
                record.update(vote=vote, reason=reason[:80], hollow=hollow, ms=ms)
                errors = 0
            except Exception as error:  # noqa: BLE001 - 單筆失敗記下來，不中止整批
                record["err"] = str(error)[:120]
                errors += 1
            with lock:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
            if errors >= 5:
                print(f"[{model}] 連續 5 次失敗，略過此模型：{record['err']}", flush=True)
                break


def cmd_run(args):
    busy = subprocess.run(["pgrep", "-af", base.BUSY], capture_output=True, text=True).stdout
    if [line for line in busy.splitlines() if "pgrep" not in line]:
        print("分析流程正在跑，拒絕執行（避免拖慢正式機、造成逾時）")
        return 2
    hour, minute = map(int, args.until.split(":"))
    deadline = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
    for directory in DIRS:
        items, done, lock = _todo(directory), _done(directory), threading.Lock()
        groups = defaultdict(list)
        for model in consensus.COMMITTEE:
            groups[model_nodes.node_of(model)].append(model)
        with open(results_path(directory), "a", encoding="utf-8") as handle:
            threads = [threading.Thread(target=_worker, args=(url, models, items, done, lock, handle, deadline)) for url, models in groups.items()]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        print(f"{directory}: 剩 {sum(1 for r, _ in items for m in consensus.COMMITTEE if (m, r['date'], r['symbol']) not in _done(directory))} 筆", flush=True)
    return 0


def cmd_status(args):
    print(remaining())
    return 0


def _votes(directory, file_name):
    out = defaultdict(dict)
    path = ROOT / directory / file_name
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not record.get("err") and record["model"] in consensus.COMMITTEE:
            out[(record["date"], record["symbol"])][record["model"]] = record["vote"]
    return out


def cmd_report(args):
    items, rows_by_dir = [], {}
    for directory in DIRS:
        samples = {(r["date"], r["symbol"]): r for r in load_samples(directory)}
        plan = {(p["date"], p["symbol"]): p for p in json.loads(plan_path(directory).read_text(encoding="utf-8"))}
        base_votes, ctx_votes = _votes(directory, "results.jsonl"), _votes(directory, results_path(directory).name) if results_path(directory).exists() else {}
        rows = []
        for key, sample in samples.items():
            before = base_votes.get(key, {})
            if len(before) < len(consensus.COMMITTEE):
                continue
            after = dict(before)
            has_ctx = bool(plan[key]["ctx_n"])
            if has_ctx:
                got = ctx_votes.get(key, {})
                if len(got) < len(consensus.COMMITTEE):
                    continue
                after = got
            advisor = sample["advisor_rating"]
            final = lambda votes: cr.final_from_votes([votes[m] for m in consensus.COMMITTEE], advisor)  # noqa: E731
            rows.append({"date": key[0], "symbol": key[1], "base": final(before), "treat": final(after), "excess": sample["excess"], "ctx": has_ctx,
                         "changed_votes": sum(1 for m in consensus.COMMITTEE if before[m] != after[m])})
        rows_by_dir[directory] = rows
        items += rows
    def show(label, subset):
        stat_b = cr.outcome_stats([{"vote": i["base"], "excess": i["excess"]} for i in subset])
        stat_t = cr.outcome_stats([{"vote": i["treat"], "excess": i["excess"]} for i in subset])
        diff = paired_spread_diff(subset)
        changed = sum(1 for i in subset if i["base"] != i["treat"])
        fmt = lambda s: "  -  " if s["spread"] is None else f"{s['spread'] * 100:+.2f}"  # noqa: E731
        band = "-" if diff is None else f"{diff[0] * 100:+.2f}pp [{diff[1] * 100:+.2f}, {diff[2] * 100:+.2f}]  P(變好)={diff[3]:.2f}"
        print(f"{label:28s} N={len(subset):4d}  原價差 {fmt(stat_b)}pp  附公告 {fmt(stat_t)}pp  差距 {band}  定案改變 {changed} 筆")
    print(f"公告窗口 {DAYS} 天；價差＝買進組均超額 − 賣出組均超額；差距的區間以日期為單位重抽 3000 次\n")
    for directory, rows in rows_by_dir.items():
        show(f"{directory.split('/')[-1]} 全部", rows)
        show(f"{directory.split('/')[-1]} 有公告者", [r for r in rows if r["ctx"]])
    show("兩組合併 全部", items)
    show("兩組合併 有公告者", [r for r in items if r["ctx"]])
    ctx = [r for r in items if r["ctx"]]
    if ctx:
        print(f"\n有公告的 {len(ctx)} 筆中：三位委員至少有一票改變 {sum(1 for r in ctx if r['changed_votes'])} 筆；"
              f"平均每筆改變 {sum(r['changed_votes'] for r in ctx) / len(ctx):.2f} 票")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--days", type=int, default=LOOKBACK_DAYS, help="往前看幾天的公告")
    sub.add_parser("prepare", parents=[common])
    run = sub.add_parser("run", parents=[common])
    run.add_argument("--until", default="19:30")
    sub.add_parser("status", parents=[common])
    sub.add_parser("report", parents=[common])
    args = parser.parse_args(argv)
    global DAYS
    DAYS = args.days
    return {"prepare": cmd_prepare, "run": cmd_run, "status": cmd_status, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
