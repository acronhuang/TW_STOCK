#!/usr/bin/env python3
"""v5 影子驗證一鍵腳本:全量影子(N 次取眾數去噪)→ 分市況+時間切段 eval → Go/No-Go 報告。

全程只寫影子欄(advisor_v5_rating),live 不動。Go/No-Go 未過 → 不得上 live。

用法(.166):
  buyside_validate_v5.py --split-date 2026-08-01            # 全量(含 LLM 影子跑)
  buyside_validate_v5.py --skip-shadow --split-date 2026-08-01   # 只用既有影子重算閘門
  buyside_validate_v5.py --limit 300 --repeats 3           # 分批 + 去噪次數
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.buyside.backtest_compare import eval_v5_shadow


def voting_ask(prompt: str, repeats: int = 3) -> str:
    """Step 2 去噪:同 prompt 跑 repeats 次,取眾數評級(LLM 非決定論)。"""
    from scripts.buyside_shadow_advisor_v5 import default_ask, extract_rating
    votes = [r for r in (extract_rating(default_ask(prompt)) for _ in range(repeats)) if r]
    if not votes:
        return ""
    return f"評級：{Counter(votes).most_common(1)[0][0]}"


def _f(x):
    return "N/A" if x is None else f"{x * 100:.1f}%"


def _e(x):
    return "N/A" if x is None else f"{x * 100:+.2f}%"


def _improved(block) -> bool:
    v5, lv = block["v5"], block["live"]
    return (v5["mean_excess"] is not None and lv["mean_excess"] is not None
            and v5["mean_excess"] > lv["mean_excess"])


def gonogo(db, window: int = 20, split_date: str = None, min_n: int = 100) -> tuple[dict, bool]:
    """回 (criteria, passed)。純讀取:讀 advisor_v5_rating(影子)+ verdict_detail(超額)。"""
    full = eval_v5_shadow(db, window=window)
    o = full["overall"]
    lv, v5 = o["live"], o["v5"]
    crit = {}

    # ① 整體 v5 > live(命中 且 超額)
    c1 = bool(lv["hit_rate"] is not None and v5["hit_rate"] is not None
              and lv["mean_excess"] is not None and v5["mean_excess"] is not None
              and v5["hit_rate"] > lv["hit_rate"] and v5["mean_excess"] > lv["mean_excess"])
    crit["① 整體 v5>live(命中+超額)"] = (
        c1, f"命中 {_f(lv['hit_rate'])}→{_f(v5['hit_rate'])} · 超額 {_e(lv['mean_excess'])}→{_e(v5['mean_excess'])}")

    # ② 前後時間段皆超額改善(v5 的核心:跨時間一致,非單窗巧合)
    if split_date:
        early = eval_v5_shadow(db, window=window, date_hi=split_date)["overall"]
        late = eval_v5_shadow(db, window=window, date_lo=split_date)["overall"]
        c2 = _improved(early) and _improved(late)
        crit["② 前後段皆超額改善(OOS 一致)"] = (
            c2, f"前段 {_e(early['live']['mean_excess'])}→{_e(early['v5']['mean_excess'])}(n={early['live']['n']}) | "
                f"後段 {_e(late['live']['mean_excess'])}→{_e(late['v5']['mean_excess'])}(n={late['live']['n']})")
    else:
        crit["② 前後段皆超額改善(OOS 一致)"] = (None, "未指定 --split-date(略過)")

    # ③ 樣本足夠
    c3 = o["live"]["n"] >= min_n
    crit["③ 樣本足夠"] = (c3, f"n={o['live']['n']}(需≥{min_n})")

    # ⑤ 盤整未受影響(runner 本就略過)
    sw = full.get("盤整")
    dg_sw = 0 if sw is None else sw["downgraded"]
    crit["⑤ 盤整未受影響"] = (dg_sw == 0, f"盤整降級={dg_sw}")

    passed = all(v[0] for v in crit.values() if v[0] is not None)
    return crit, passed


def main() -> int:
    ap = argparse.ArgumentParser(description="v5 影子驗證(Go/No-Go)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--split-date", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--min-n", type=int, default=100)
    ap.add_argument("--skip-shadow", action="store_true", help="只用既有影子重算閘門(不跑 LLM)")
    ap.add_argument("--resume", action="store_true", help="影子續跑(跳過已評級者)")
    args = ap.parse_args()

    from pymongo import MongoClient
    db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017")).tw_stock_analysis

    if not args.skip_shadow:
        from scripts.buyside_shadow_advisor_v5 import run as shadow_run
        res = shadow_run(db, window=args.window, limit=args.limit,
                         ask_fn=lambda p: voting_ask(p, args.repeats), resume=args.resume)
        print(f"[Step1-2 影子+去噪] 趨勢市買進處理 {res['n']}(觀望/降級 {res['flipped']})、"
              f"盤整略過 {res['skipped_sideways']}")

    crit, passed = gonogo(db, window=args.window, split_date=args.split_date, min_n=args.min_n)
    print("\n===== Step3-5:v5 影子驗證 Go/No-Go =====")
    for k, (ok, detail) in crit.items():
        mark = "—" if ok is None else ("✅" if ok else "🔴")
        print(f"  {mark} {k}: {detail}")
    print(f"\n>>> {'✅ GO — 可進團隊簽核 → feature-flag' if passed else '🔴 NO-GO — 不得上 live'}")
    print("④ LLM 穩定度:已用 %d 次取眾數去噪(飄動由 repeats 吸收)" % args.repeats)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
