#!/usr/bin/env python3
"""用 TWSE 官方除權息表補 adjustment_factors 缺漏的事件（只新增缺列，不覆蓋既有係數）。

用法：python scripts/fill_exright_factors.py [--days N | --start YYYY-MM-DD] [--apply]
預設 dry-run；--apply 才寫入。新增列 updated_at 為現在，隔天 02:00 的 backfill_adj_close --changed-only 會套用到 adj_close。
只涵蓋上市（TWSE）；上櫃另無對應來源。
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from pymongo import MongoClient, UpdateOne

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_gap.exright_factors import TWT49U, agreement, missing_factors, parse_exright_factors

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def collect(session, start, end, pause=1.0):
    from time import sleep

    events, skipped = [], []
    for year in range(start.year, end.year + 1):
        first, last = max(start, datetime(year, 1, 1)), min(end, datetime(year, 12, 31))
        reply = session.get(TWT49U, params={"startDate": first.strftime("%Y%m%d"), "endDate": last.strftime("%Y%m%d"),
                                            "response": "json"}, headers={"User-Agent": UA}, timeout=60)
        reply.raise_for_status()
        parsed = parse_exright_factors(reply.json(), first, last)
        events += parsed["events"]
        skipped += parsed["skipped"]
        sleep(pause)
    return events, skipped


def run(db, session, start, end, apply=False, pause=1.0, now=None):
    events, skipped = collect(session, start, end, pause)
    existing = {(row["stock_id"], row["ex_date"]): row.get("factor") for row in db["adjustment_factors"].find(
        {"ex_date": {"$gte": start, "$lte": end}}, {"_id": 0, "stock_id": 1, "ex_date": 1, "factor": 1})}
    numeric = {key: float(value.to_decimal() if hasattr(value, "to_decimal") else value)
               for key, value in existing.items() if value is not None}
    priced = set(db["stock_price"].distinct("symbol"))
    gaps = missing_factors(events, set(existing), priced)
    now = now or datetime.now()
    operations = [UpdateOne({"stock_id": event["stock_id"], "ex_date": event["ex_date"]},
                            {"$setOnInsert": {**event, "source": "TWSE_TWT49U", "updated_at": now}}, upsert=True)
                  for event in gaps]
    if apply and operations:
        db["adjustment_factors"].bulk_write(operations, ordered=False)
    return {"official_events": len(events), "skipped": len(skipped), "missing": len(gaps), "applied": apply,
            "agreement_with_existing": agreement(events, numeric)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--days", type=int, help="只看最近 N 天（優先於 --start）")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days) if args.days else datetime.fromisoformat(args.start)
    db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
    try:
        result = run(db, requests.Session(), start, end, apply=args.apply)
    except (requests.RequestException, ValueError) as exc:
        print(f"FAIL 官方除權息表取得失敗：{exc}")
        return 1
    print(result)
    if not args.apply:
        print("[DRY-RUN] 未寫入，加 --apply 執行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
