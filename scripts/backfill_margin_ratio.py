#!/usr/bin/env python3
"""把融資融券餘額換算成券資比，寫入 stock_factors.short_margin_ratio。預設 dry-run，--apply 才寫。

evening_pipeline 於因子重算後執行最近 N 日；--since 用於一次性回補歷史。
只更新已存在的 (symbol, date) 因子文件，不建立新文件。
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.chip_analysis import margin_ratio  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_MARGIN_PURCHASE_SHORT_SALE, COLL_STOCK_FACTORS  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="最近 N 個日曆日（預設 7）")
    parser.add_argument("--since", help="起日 YYYY-MM-DD，優先於 --days")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    since = datetime.strptime(args.since, "%Y-%m-%d") if args.since else datetime.now() - timedelta(days=args.days)
    margin = db[COLL_MARGIN_PURCHASE_SHORT_SALE]
    days = sorted(margin.distinct("date", {"date": {"$gte": since}}))

    total = matched = 0
    for day in days:
        docs = list(margin.find({"date": day}, {"code": 1, "margin_balance": 1, "short_balance": 1, "_id": 0}))
        total += len(docs)
        if not args.apply:
            sample = [(d["code"], margin_ratio.short_margin_ratio(d.get("margin_balance"), d.get("short_balance")))
                      for d in docs[:3]]
            print(f"{day:%Y-%m-%d} 融資券 {len(docs)} 檔 例 {sample}")
            continue
        result = margin_ratio.apply_day(db[COLL_STOCK_FACTORS], day, docs)
        matched += result.matched_count if result else 0
    print(f"days={len(days)} margin_rows={total} factor_docs_matched={matched} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
