#!/usr/bin/env python3
"""PTT Stock 板每日討論熱度 → social_buzz。預設 dry-run，--apply 才寫。

走訪列表頁統計「標題提及個股的文章數、推文數、標題情緒」；--days 控制往回幾天（每天約 40 頁，禮貌性間隔 1 秒）。
列表頁可回溯，所以停機漏掉的日子可用較大的 --days 補抓。
"""
import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ASCENDING, UpdateOne  # noqa: E402

from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_SOCIAL_BUZZ, COLL_SYSTEM_HEARTBEAT  # noqa: E402
from src.ingest import ptt  # noqa: E402

BUZZ_WINDOW = 20


def load_universe(db) -> list[tuple[str, str]]:
    docs = db["taiwan_stock_info"].find({}, {"stock_id": 1, "stock_name": 1, "_id": 0})
    return [(d["stock_id"], d["stock_name"]) for d in docs
            if re.fullmatch(r"\d{4}", str(d.get("stock_id", ""))) and d.get("stock_name")]


def history_for(collection, rows: list[dict]) -> tuple[dict, set]:
    low = min(r["date"] for r in rows) - timedelta(days=40)
    docs = list(collection.find({"source": ptt.SOURCE, "date": {"$gte": low, "$lt": max(r["date"] for r in rows)}},
                                {"stock_id": 1, "date": 1, "mentions": 1, "_id": 0}))
    return {(d["stock_id"], d["date"]): d["mentions"] for d in docs}, {d["date"] for d in docs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=2, help="往回抓幾天（含今天），預設 2")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    now = datetime.now()
    posts = ptt.crawl(ptt.fetch_page, today=now.date(), days_back=args.days)
    rows = ptt.aggregate(posts, ptt.Matcher(load_universe(db)))
    collection = db[COLL_SOCIAL_BUZZ]
    if rows:
        history, known_dates = history_for(collection, rows)
        ptt.attach_buzz(rows, history, known_dates, window=BUZZ_WINDOW)
    top = sorted(rows, key=lambda r: -r["mentions"])[:5]
    print(f"posts={len(posts)} stock_days={len(rows)} mode={'apply' if args.apply else 'dry-run'} "
          f"top={[(r['stock_id'], r['mentions']) for r in top]}")
    if not args.apply:
        return 0
    if not posts:
        print("⚠️ 沒有抓到任何文章，視為來源異常，不寫入")
        return 1
    collection.create_index([("stock_id", ASCENDING), ("date", ASCENDING), ("source", ASCENDING)],
                            unique=True, name="uq_stock_date_source")
    if rows:
        collection.bulk_write([UpdateOne({"stock_id": r["stock_id"], "date": r["date"], "source": r["source"]},
                                         {"$set": {**r, "updated_at": now}}, upsert=True) for r in rows], ordered=False)
    db[COLL_SYSTEM_HEARTBEAT].update_one(
        {"_id": "social_buzz"}, {"$set": {"last_run": now, "status": "ok", "posts": len(posts), "stock_days": len(rows)}},
        upsert=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
