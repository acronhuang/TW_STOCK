#!/usr/bin/env python3
"""角色簡化影子測試：同一批股票用不同角色編制各跑一次，比較最後裁決。只讀，不寫資料庫。

編制（arm）：
  P   現行：價值、風控、籌碼都用規則模板（2026-10-21 起的預設）
  P2  與 P 完全相同再跑一次，量測「重跑本身」的雜訊（同輸入也會偶爾翻票）
  F   六個角色全走 LLM（TEAM_RULE_ROLES=""）
  V   價值角色走 LLM、風控與籌碼用模板（2026-10-21 之前的編制）
判讀以 P↔P2 的一致率當底線：F 或 V 與 P 的一致率區間若與它重疊，差異就分不出是編制還是雜訊。
輸出：logs/rule_roles_shadow/shadow_YYYYMMDD.jsonl（可續跑）與 report_YYYYMMDD.md。

用法：
  python scripts/rule_roles_shadow.py --n 48            抽樣、跑全部編制、寫報告
  python scripts/rule_roles_shadow.py --report-only     只用既有 jsonl 重寫報告
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ARMS = {"P": None, "P2": None, "F": "", "V": "risk-manager,chip-analyst"}  # None＝不設環境變數；""＝全部回 LLM
COMPARISONS = (("P", "P2", "雜訊底線：同編制再跑一次"), ("P", "F", "現行 vs 六角色全 LLM"),
               ("V", "P", "價值角色走 LLM（舊編制）vs 現行"), ("V", "F", "價值角色走 LLM（舊編制）vs 六角色全 LLM"))
OUT_DIR = ROOT / "logs" / "rule_roles_shadow"


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - half), min(1.0, center + half)


def by_arm(rows):
    table = {}
    for row in rows:
        table.setdefault(row["arm"], {})[row["symbol"]] = row
    return table


def compare(table, a, b):
    """回 (同裁決, 可比檔數, 買進賣出對翻, 三票全同)。沒有裁決的檔不比。"""
    same = total = flips = votes_same = 0
    for symbol, left in table.get(a, {}).items():
        right = table.get(b, {}).get(symbol)
        if not right or not left.get("final") or not right.get("final"):
            continue
        total += 1
        same += left["final"] == right["final"]
        flips += {left["final"], right["final"]} == {"買進", "賣出"}
        votes_same += [v[1] for v in left.get("votes", [])] == [v[1] for v in right.get("votes", [])]
    return same, total, flips, votes_same


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else None


def summarize(rows, stamp):
    table = by_arm(rows)
    symbols = {r["symbol"] for r in rows}
    lines = [f"# 角色簡化影子測試 {stamp}", "", f"共 {len(symbols)} 檔；有結果的編制：{'、'.join(a for a in ARMS if a in table)}。", "", "## 各編制的最後裁決分佈", ""]
    for arm in ARMS:
        if arm in table:
            count = Counter(r.get("final") or "無裁決" for r in table[arm].values())
            wall = median([r["wall"] for r in table[arm].values() if r.get("wall") is not None])
            lines.append(f"- {arm}：" + "、".join(f"{k}{v}" for k, v in sorted(count.items())) + (f"；每檔耗時中位數 {wall:.0f} 秒" if wall is not None else ""))
    lines += ["", "## 一致率（最後裁決相同 / 可比檔數；括號是 Wilson 95% 區間）", "",
              "| 比較 | 一致 | 買進賣出對翻 | 三票全同 |", "|---|---|---:|---:|"]
    for a, b, label in COMPARISONS:
        if a not in table or b not in table:
            continue
        same, total, flips, votes_same = compare(table, a, b)
        ci = wilson(same, total)
        agree = f"{same}/{total} = {same / total * 100:.0f}%（{ci[0] * 100:.0f}~{ci[1] * 100:.0f}%）" if total else "無可比檔"
        lines.append(f"| {a}↔{b} {label} | {agree} | {flips} | {votes_same}/{total} |")
    lines += ["", "判讀：F 或 V 與 P 的一致率區間若與 P↔P2 重疊，差異分不出是編制還是重跑雜訊；買進賣出對翻是最嚴重的差異，逐檔看 jsonl。"]
    failed = [(r["arm"], r["symbol"], r.get("error")) for r in rows if r.get("error")]
    if failed:
        lines += ["", f"## 失敗 {len(failed)} 筆", ""] + [f"- {a} {s}：{e}" for a, s, e in failed[:20]]
    return "\n".join(lines) + "\n"


def load_rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_arm(arm, symbols, analyze, out_path, done, workers=2, clock=time.time):
    """同一編制內的股票並行（環境變數是全域的，所以編制之間不可並行）。已完成的 (編制, 代號) 略過。"""
    value = ARMS[arm]
    previous = os.environ.get("TEAM_RULE_ROLES")
    if value is None:
        os.environ.pop("TEAM_RULE_ROLES", None)
    else:
        os.environ["TEAM_RULE_ROLES"] = value

    def one(symbol):
        started = clock()
        row = {"arm": arm, "symbol": symbol}
        try:
            result = analyze(symbol, quick=False)
            consensus = result.get("consensus") or {}
            row.update(final=consensus.get("final"), votes=[(v["model"].split(":")[0], v["vote"]) for v in consensus.get("votes", [])],
                       models=result.get("models"), value_head=((result.get("reports") or {}).get("value-analyst") or "")[:80])
        except Exception as exc:  # 單檔失敗不中斷整批
            row.update(final=None, error=f"{type(exc).__name__}: {exc}"[:200])
        row["wall"] = round(clock() - started, 1)
        return row

    try:
        todo = [s for s in symbols if (arm, s) not in done]
        with ThreadPoolExecutor(max_workers=workers) as pool, out_path.open("a", encoding="utf-8") as out:
            for row in pool.map(one, todo):
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
    finally:
        if previous is None:
            os.environ.pop("TEAM_RULE_ROLES", None)
        else:
            os.environ["TEAM_RULE_ROLES"] = previous


def pick_symbols(n, seed, source_date):
    from pymongo import MongoClient

    db = MongoClient()["tw_stock_analysis"]["team_analysis"]
    pool = sorted({d["symbol"] for d in db.find({"date": source_date, "final_verdict": {"$nin": [None, ""]}}, {"symbol": 1})})
    return random.Random(seed).sample(pool, min(n, len(pool)))


def main(argv=None, analyze=None, now=datetime.now):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--source-date", default="2026-10-16", help="從這天已有最後裁決的股票裡抽樣")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--symbols", nargs="+", help="指定股票（略過抽樣）")
    args = parser.parse_args(argv)
    moment = now()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"shadow_{moment:%Y%m%d}.jsonl"

    if not args.report_only:
        if subprocess.run(["pgrep", "-f", r"team_daily_verified\.py"], capture_output=True).returncode == 0 and analyze is None:
            print("⏭ 團隊分析進行中，影子測試不與它搶 GPU（刻意跳過，exit 75）")
            return 75
        if analyze is None:
            from scripts import team_daily_verified as tdv
            tdv.MACRO_CACHE_ON = False  # 總經快取會讓先跑的編制影響後跑的，影子測試要每檔獨立
            analyze = tdv.analyze_symbol
        unknown = [a for a in args.arms.split(",") if a not in ARMS]
        if unknown:
            parser.error(f"未知編制：{unknown}")
        symbols = args.symbols or pick_symbols(args.n, args.seed, datetime.strptime(args.source_date, "%Y-%m-%d"))
        done = {(r["arm"], r["symbol"]) for r in load_rows(out_path) if not r.get("error")}
        for arm in args.arms.split(","):
            print(f"== 編制 {arm}：{len([s for s in symbols if (arm, s) not in done])} 檔 {now():%H:%M:%S}", flush=True)
            run_arm(arm, symbols, analyze, out_path, done, args.workers)

    report = summarize(load_rows(out_path), f"{moment:%Y-%m-%d}")
    (args.out_dir / f"report_{moment:%Y%m%d}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
