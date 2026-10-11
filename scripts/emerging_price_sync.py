#!/usr/bin/env python3
"""興櫃每日行情同步 → emerging_price。預設 dry-run，--apply 才寫。

來源只給最新交易日（無歷史端點），所以必須每個交易日收盤後執行才不會漏日。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ASCENDING  # noqa: E402

from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_EMERGING_PRICE  # noqa: E402
from src.ingest import emerging  # noqa: E402

MIN_EXPECTED_ROWS = 200   # 興櫃約 360 檔；遠低於此代表來源異常，不寫入以免留下殘缺日


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    docs = emerging.parse(emerging.fetch(), datetime.now())
    days = sorted({d["date"].strftime("%Y-%m-%d") for d in docs})
    print(f"rows={len(docs)} dates={days} mode={'apply' if args.apply else 'dry-run'}")
    if len(docs) < MIN_EXPECTED_ROWS:
        print(f"⚠️ 筆數低於 {MIN_EXPECTED_ROWS}，視為來源異常，不寫入")
        return 1
    if args.apply:
        collection = get_db()[COLL_EMERGING_PRICE]
        collection.create_index([("stock_id", ASCENDING), ("date", ASCENDING)], unique=True, name="uq_stock_date")
        result = emerging.upsert(collection, docs)
        print(f"upserted={result.upserted_count} modified={result.modified_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
