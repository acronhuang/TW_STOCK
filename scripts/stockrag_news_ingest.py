#!/usr/bin/env python3
"""新聞與重大訊息入庫（stockrag.news_docs）。可續跑：已存在的 key 不重算嵌入。

用法：
  stockrag_news_ingest.py --dry-run                 # 只統計會新增幾筆
  stockrag_news_ingest.py --days 90                 # 重大訊息近 90 天 + 媒體新聞快取（預設）
  stockrag_news_ingest.py --days 4 --source major   # 每日排程用：只補近幾天的重大訊息
嵌入走 Ollama(.28，CPU，與資安 RAG 共用)，約 0.5 秒一筆，故預設限速。
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne  # noqa: E402

import stockrag_news as news  # noqa: E402
import stockrag_search as base  # noqa: E402

BATCH = 100


def candidates(db, source: str, days: int) -> list[dict]:
    docs: dict[str, dict] = {}
    if source in ("major", "all"):
        since = datetime.now() - timedelta(days=days)
        for row in db["major_news"].find({"date": {"$gte": since}}):
            doc = news.major_doc(row)
            if doc:
                docs[doc["key"]] = doc
    if source in ("media", "all"):
        for row in db["media_news"].find({}).sort("fetched_at", ASCENDING):
            doc = news.media_doc(row)
            if doc and doc["key"] not in docs:      # 同一組標題只留最早看到的時間
                docs[doc["key"]] = doc
    return sorted(docs.values(), key=lambda d: d["doc_date"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--source", choices=["major", "media", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    client = MongoClient("mongodb://localhost:27017/")
    wanted = candidates(client["tw_stock_analysis"], args.source, args.days)
    col = client["stockrag"][news.COLLECTION]
    col.create_index([("key", ASCENDING)], unique=True)
    col.create_index([("symbol", ASCENDING), ("doc_date", DESCENDING)])
    existing = {d["key"] for d in col.find({"key": {"$in": [w["key"] for w in wanted]}}, {"key": 1})}
    todo = [w for w in wanted if w["key"] not in existing]
    if args.limit:
        todo = todo[:args.limit]
    print(f"候選 {len(wanted)} 則，已在庫 {len(existing)}，待嵌入 {len(todo)}（來源 {args.source}，近 {args.days} 天）", flush=True)
    if args.dry_run or not todo:
        return 0

    ops, done, failed = [], 0, 0
    for doc in todo:
        try:
            vector = base.embed(doc["content"])
        except Exception as error:  # noqa: BLE001 - 單筆失敗留給下一輪
            failed += 1
            print(f"  ! {doc['key']}: {str(error)[:60]}", flush=True)
            continue
        ops.append(UpdateOne({"key": doc["key"]}, {"$set": {**doc, "embedding": vector, "updated_at": datetime.now()}}, upsert=True))
        done += 1
        if len(ops) >= BATCH:
            col.bulk_write(ops, ordered=False)
            ops = []
            print(f"  … {done}/{len(todo)}", flush=True)
        time.sleep(args.sleep)
    if ops:
        col.bulk_write(ops, ordered=False)
    print(f"完成：新增 {done}，失敗 {failed}；庫內共 {col.count_documents({}):,} 則", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
