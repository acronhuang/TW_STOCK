#!/usr/bin/env python3
"""每日重點個股新聞情緒 → news_sentiment（並順手刷新 media_news 快取）。預設 dry-run，--apply 才寫。

追蹤名單 = 持倉 + 核心池 + 最新 VCP 候選（約 100~300 檔）。全市場仍由每週五的 media_news_sync 負責，
兩者都會把當日情緒分數寫進 news_sentiment，所以重點個股每天有一筆、其餘每週一筆。
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ASCENDING  # noqa: E402

from src.analysis.news_evidence import google_titles  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_MEDIA_NEWS,
    COLL_NEWS_SENTIMENT,
    COLL_SYSTEM_HEARTBEAT,
    COLL_VCP_CANDIDATES,
)
from src.ingest import news_sentiment  # noqa: E402

MIN_SUCCESS_RATIO = 0.5   # 超過一半查不到標題，多半是被 Google 限流，不是真的沒新聞


def focus_universe(db) -> list[tuple[str, str]]:
    latest = db[COLL_VCP_CANDIDATES].find_one({}, {"scan_date": 1}, sort=[("scan_date", -1)])
    vcp = list(db[COLL_VCP_CANDIDATES].find({"scan_date": latest["scan_date"]}, {"symbol": 1})) if latest else []
    codes = news_sentiment.focus_codes(list(db["portfolio_positions"].find({}, {"symbol": 1})),
                                       db["core_watchlist"].find_one({"_id": "current"}), vcp)
    names = {d["stock_id"]: d.get("stock_name") for d in db["taiwan_stock_info"].find(
        {"stock_id": {"$in": codes}}, {"stock_id": 1, "stock_name": 1})}
    return [(code, names[code]) for code in codes if names.get(code)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="只處理前 N 檔（測試用）")
    parser.add_argument("--sleep", type=float, default=0.8, help="每檔間隔秒數（禮貌性節流）")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    now = datetime.now()
    targets = focus_universe(db)[:args.limit] if args.limit else focus_universe(db)
    docs, empty = [], 0
    for code, name in targets:
        titles = google_titles(name, max_items=10)
        if not titles:
            empty += 1
        else:
            docs.append(news_sentiment.build_doc(code, name, titles, now, now))
        time.sleep(args.sleep)
    success = len(docs) / len(targets) if targets else 1.0
    print(f"targets={len(targets)} with_news={len(docs)} empty={empty} mode={'apply' if args.apply else 'dry-run'}")
    for doc in docs[:3]:
        print(f"  {doc['stock_id']} {doc['name']} count={doc['count']} score={doc['score']} {doc['label']}")
    if not args.apply:
        return 0
    if targets and success < MIN_SUCCESS_RATIO:
        print(f"⚠️ 成功率 {success:.0%} 低於 {MIN_SUCCESS_RATIO:.0%}，疑似被限流，不寫入")
        return 1
    collection = db[COLL_NEWS_SENTIMENT]
    collection.create_index([("stock_id", ASCENDING), ("date", ASCENDING), ("source", ASCENDING)],
                            unique=True, name="uq_stock_date_source")
    news_sentiment.upsert(collection, docs)
    for doc in docs:
        db[COLL_MEDIA_NEWS].update_one({"stock_id": doc["stock_id"]},
                                       {"$set": {"stock_id": doc["stock_id"], "name": doc["name"],
                                                 "titles": doc["titles"], "fetched_at": now}}, upsert=True)
    db[COLL_SYSTEM_HEARTBEAT].update_one(
        {"_id": "news_sentiment"}, {"$set": {"last_run": now, "status": "ok", "with_news": len(docs), "empty": empty}},
        upsert=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
