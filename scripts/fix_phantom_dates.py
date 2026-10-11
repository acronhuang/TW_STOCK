#!/usr/bin/env python3
"""清理非交易日被標上資料的列（抓取日被誤當資料日）。預設 dry-run，--apply 才改資料。

動作由 src/data_gap/phantom.py 規劃：前一交易日沒資料 → 改標回前一交易日（補回缺日）；
已驗證為精確複本的表 → 刪除；其餘表 → 併入前一交易日後刪除。
融資融券請先用 backfill_margin_by_date.py 以官方按日期資料覆蓋，再執行本腳本。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne  # noqa: E402

from src.config import get_db  # noqa: E402
from src.data_gap import phantom  # noqa: E402


def _day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def apply_action(collection, action: dict) -> int:
    source = _day(action["from"])
    if action["op"] == "delete":
        return collection.delete_many({"date": source}).deleted_count
    target = _day(action["to"])
    if action["op"] == "relabel":
        return collection.update_many({"date": source}, {"$set": {"date": target}}).modified_count
    key = action["key"]
    operations = []
    for doc in collection.find({"date": source}):
        doc.pop("_id", None)
        operations.append(UpdateOne({key: doc[key], "date": target}, {"$set": {**doc, "date": target}}, upsert=True))
    if operations:
        collection.bulk_write(operations, ordered=False)
    collection.delete_many({"date": source})
    return len(operations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="2026-03-01", help="只處理此日期（含）之後的假日列")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    trading = sorted(d["date"] for d in db["trading_dates"].find({}, {"date": 1}))
    total = 0
    for name in phantom.COLLECTIONS:
        collection = db[name]
        stamped = [d.strftime("%Y-%m-%d") for d in collection.distinct("date", {"date": {"$type": "date"}})]
        days = phantom.phantom_days(stamped, trading, args.since)
        actions = phantom.plan(name, days, trading, lambda day: collection.count_documents({"date": _day(day)}))
        for action in actions:
            rows = collection.count_documents({"date": _day(action["from"])})
            detail = f"{action['from']} → {action.get('to', '(刪除)')}"
            if args.apply:
                done = apply_action(collection, action)
                print(f"{name:28} {action['op']:8} {detail}  rows={rows} applied={done}")
            else:
                print(f"{name:28} {action['op']:8} {detail}  rows={rows}")
            total += 1
    print(f"actions={total} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
