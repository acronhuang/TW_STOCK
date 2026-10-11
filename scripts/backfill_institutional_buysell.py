#!/usr/bin/env python3
"""回補 institutional_flow 的買進／賣出分列（foreign/trust/dealer × buy/sell）。預設 dry-run，--apply 才寫。

來源為指定日期的 TWSE T86 與 TPEX 三大法人表；只對既有 (stock_id, date) 文件 $set 六個分列欄位，
不改淨買賣超、不新增文件。可中斷續跑：已有分列的日子（>=90% 文件）會略過。
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne  # noqa: E402

from institutional_backfill import fetch_tpex_dated  # noqa: E402
from src.chip_analysis.inst_buysell import FIELDS  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_INSTITUTIONAL_FLOW  # noqa: E402
from twse_daily_update import fetch_twse_institutional  # noqa: E402

DONE_RATIO = 0.9


def day_records(day) -> list[dict]:
    records = []
    for label, fetch in (("TWSE", lambda: fetch_twse_institutional(day.strftime("%Y-%m-%d"))),
                         ("TPEX", lambda: fetch_tpex_dated(day))):
        try:
            records += [r for r in fetch() if r["date"].date() == day.date()]
        except Exception as error:  # noqa: BLE001 - 單日單來源失敗不中斷整批
            print(f"  ⚠️ {day:%Y-%m-%d} {label} 失敗：{str(error)[:90]}")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", help="起日 YYYY-MM-DD（預設 30 天前）")
    parser.add_argument("--end", help="迄日 YYYY-MM-DD（預設今天）")
    parser.add_argument("--limit", type=int, help="最多處理幾個交易日")
    parser.add_argument("--sleep", type=float, default=1.5, help="每個來源請求間隔秒數")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    flow = get_db()[COLL_INSTITUTIONAL_FLOW]
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else end - timedelta(days=30)
    days = sorted(flow.distinct("date", {"date": {"$gte": start, "$lte": end}}))
    if args.limit:
        days = days[:args.limit]

    updated = skipped = empty = 0
    for index, day in enumerate(days, 1):
        total = flow.count_documents({"date": day})
        have = flow.count_documents({"date": day, "foreign_buy": {"$exists": True}})
        if total and have >= DONE_RATIO * total:
            skipped += 1
            continue
        records = day_records(day)
        operations = [UpdateOne({"stock_id": r["stock_id"], "date": r["date"]},
                                {"$set": {k: r[k] for k in FIELDS}}, upsert=False)
                      for r in records if all(k in r for k in FIELDS)]
        time.sleep(args.sleep * 2)
        if not operations:
            empty += 1
            print(f"  {day:%Y-%m-%d} 沒有可用分列（來源空或欄位核對失敗）")
            continue
        if args.apply:
            updated += flow.bulk_write(operations, ordered=False).modified_count
        print(f"  [{index}/{len(days)}] {day:%Y-%m-%d} 來源 {len(records)} 筆 可寫 {len(operations)} 筆 (已有 {have}/{total})")
    print(f"days={len(days)} updated={updated} skipped_done={skipped} empty={empty} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
