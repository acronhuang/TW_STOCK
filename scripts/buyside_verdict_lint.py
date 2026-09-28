#!/usr/bin/env python3
"""P2 影子一致性 lint CLI — 對 team_analysis 買進列寫 shadow_lint(附加式,不動 live)。

用法:
  python scripts/buyside_verdict_lint.py --dry-run   # 只統計不寫
  python scripts/buyside_verdict_lint.py             # 寫 shadow_lint 欄
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pymongo import MongoClient  # noqa: E402

from src.analysis.buyside.verdict_lint import run_lint  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只統計不寫入")
    ap.add_argument("--all", action="store_true", help="含非買進(預設只買進)")
    ap.add_argument("--mongo", default="mongodb://localhost:27017/")
    args = ap.parse_args()

    db = MongoClient(args.mongo)["tw_stock_analysis"]
    agg = run_lint(db, only_buy=not args.all, dry_run=args.dry_run)
    n = agg["n"] or 1
    mode = "DRY-RUN(未寫)" if args.dry_run else "已寫 shadow_lint"
    print(f"[{mode}] 買進 verdict n={agg['n']}")
    print(f"  ① 追高       {agg['chase_entry']:>4} ({agg['chase_entry']/n*100:.1f}%)")
    print(f"  ② 買進0張     {agg['buy_zero_shares']:>4} ({agg['buy_zero_shares']/n*100:.1f}%)")
    print(f"  ③ 風報比<1    {agg['bad_risk_reward']:>4} ({agg['bad_risk_reward']/n*100:.1f}%)")
    print(f"  ④ 含合議壞票  {agg['any_hollow']:>4} ({agg['any_hollow']/n*100:.1f}%)")
    print(f"  ✅ 零紅旗(乾淨){agg['clean']:>4} ({agg['clean']/n*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
