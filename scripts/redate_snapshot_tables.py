#!/usr/bin/env python3
"""依真實日期重建六張快照型表（零股、盤後定價、外資 Top20、借券、ETF 排行、停資券）。預設 dry-run。

來源可以是正式庫本身，或清理前備份還原出的暫存庫（--source-db）。每個標記日依 src/data_gap/redate.py 對應到真實日，
先寫成 <表>_redated，核對後才用 --apply 換上；原表改名為 <表>_pre_redate 保留，確認無誤後再手動刪除。
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime  # noqa: E402

from pymongo import ASCENDING, DESCENDING, MongoClient  # noqa: E402
from pymongo.errors import BulkWriteError  # noqa: E402

from src.config import get_db  # noqa: E402
from src.data_gap import redate  # noqa: E402

KEYS = {"odd_lot_trading": "stock_id", "after_hours_trading": "stock_id", "foreign_top20": "stock_id",
        "securities_lending": "twse_code", "etf_dca_rank": "rank", "margin_suspension": "stock_id"}
# 與 twse_openapi_sync 各 sync 函式建立的索引相同；索引鍵相同但選項不同會讓它們的 create_index 報錯
STANDARD_INDEX = {"etf_dca_rank": [("date", DESCENDING)]}
BUILD_INDEX = "uq_build"
CHUNK = 5000


def _day(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def rebuild(source, destination, key: str, mapping: dict[str, str | None]) -> dict:
    """把 source 每個標記日的文件改成對應的真實日後寫入 destination；同一目標日的重複列以唯一索引擋掉。"""
    destination.create_index([(key, ASCENDING), ("date", DESCENDING)], unique=True, name=BUILD_INDEX)
    copied = skipped = 0
    for stamped, target in sorted(mapping.items()):
        if target is None:
            skipped += source.count_documents({"date": _day(stamped)})
            continue
        batch = []
        for doc in source.find({"date": _day(stamped)}):
            doc.pop("_id", None)
            doc["date"] = _day(target)
            batch.append(doc)
            if len(batch) >= CHUNK:
                copied += _insert(destination, batch)
                batch = []
        copied += _insert(destination, batch)
    destination.drop_index(BUILD_INDEX)
    destination.create_index(STANDARD_INDEX.get(destination.name.removesuffix("_redated"), [(key, ASCENDING), ("date", DESCENDING)]))
    return {"copied": copied, "skipped_no_target": skipped, "days": len(destination.distinct("date"))}


def _insert(collection, docs: list[dict]) -> int:
    if not docs:
        return 0
    try:
        return len(collection.insert_many(docs, ordered=False).inserted_ids)
    except BulkWriteError as error:
        if any(e.get("code") != 11000 for e in error.details.get("writeErrors", [])):
            raise
        return error.details.get("nInserted", 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", help="來源資料庫名稱（預設為正式庫）")
    parser.add_argument("--apply", action="store_true", help="核對後換上重建的表（原表改名保留）")
    args = parser.parse_args(argv)

    prod = get_db()
    source_db = MongoClient()[args.source_db] if args.source_db else prod
    trading = sorted(d["date"] for d in prod["trading_dates"].find({}, {"date": 1}))
    for name, key in KEYS.items():
        source = source_db[name]
        stamped = [d.strftime("%Y-%m-%d") for d in source.distinct("date", {"date": {"$type": "date"}})]
        mapping = redate.day_map(stamped, trading, redate.SEMANTICS[name])
        moved = sum(1 for s, t in mapping.items() if s != t)
        print(f"{name:22} stamped_days={len(stamped)} relabelled={moved} no_target={sum(1 for t in mapping.values() if t is None)}")
        if not args.apply:
            continue
        rebuilt = prod[f"{name}_redated"]
        rebuilt.drop()
        stats = rebuild(source, rebuilt, key, mapping)
        print(f"   rebuilt rows={stats['copied']} days={stats['days']} (source rows={source.estimated_document_count()})")
        prod[name].rename(f"{name}_pre_redate", dropTarget=True)
        rebuilt.rename(name)
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
