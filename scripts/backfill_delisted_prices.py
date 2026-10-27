#!/usr/bin/env python3
"""補下市 4 碼普通股的歷史價格（FinMind TaiwanStockPrice，每檔一次請求；只新增缺列，不覆蓋既有列）。

用法：python scripts/backfill_delisted_prices.py --snapshot <來源快照ID> [--start 2013-01-01] [--limit N] [--apply]
預設 dry-run。下市日取自既有來源快照（TaiwanStockDelisting）；新列只含 close/adj_close，
還原欄位由 backfill_adj_close --changed-only 補算。
"""
import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_held_prices import URL, to_doc

from src.data_gap.delisted import plan_history

HEADROOM = 20


def insert_operation(doc, now):
    fields = {**doc, "adj_close": doc["close"], "updated_at": now}
    return UpdateOne({"symbol": doc["symbol"], "date": doc["date"]}, {"$setOnInsert": fields}, upsert=True)


def run(db, facts, token, usage, start, apply=False, limit=None, session=None, now=None):
    session = session or requests.Session()
    now = now or datetime.now()
    symbols = sorted({fact["symbol"] for fact in facts})
    last = {row["_id"]: row["last"].date() for row in db["stock_price"].aggregate(
        [{"$match": {"symbol": {"$in": symbols}}}, {"$group": {"_id": "$symbol", "last": {"$max": "$date"}}}])}
    plan = plan_history(facts, last, start)[:limit]
    if usage is None or usage[1] - usage[0] < len(plan) + HEADROOM:
        return {"status": "aborted", "reason": "FinMind quota unknown or insufficient", "planned": len(plan)}
    inserted, report, stopped = 0, [], None
    for item in plan:
        reply = session.get(URL, params={"dataset": "TaiwanStockPrice", "data_id": item["symbol"],
                                         "start_date": item["from"].isoformat(), "end_date": item["to"].isoformat()},
                            headers={"Authorization": f"Bearer {token}"}, timeout=40)
        if reply.status_code != 200:
            stopped = {"symbol": item["symbol"], "http_status": reply.status_code}
            break
        docs = [doc for doc in (to_doc(item["symbol"], row) for row in reply.json().get("data") or []) if doc]
        docs = [doc for doc in docs if item["from"] <= doc["date"].date() <= item["to"]]
        if apply and docs:
            db["stock_price"].bulk_write([insert_operation(doc, now) for doc in docs], ordered=False)
        inserted += len(docs)
        report.append({"symbol": item["symbol"], "rows": len(docs)})
    return {"status": "stopped" if stopped else "ok", "planned": len(plan), "rows": inserted, "applied": apply,
            "stopped": stopped, "empty": [r["symbol"] for r in report if not r["rows"]]}


def main(argv=None) -> int:
    from dotenv import load_dotenv

    from src.config import get_db
    from src.ops.finmind_usage import fetch_usage

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    token = os.getenv("FINMIND_API_TOKEN", "")
    db = get_db()
    document = db["quant_source_evidence"].find_one({"_id": args.snapshot})
    if document is None:
        print("FAIL 找不到來源快照")
        return 1
    facts = [{"symbol": fact["symbol"], "delisted_on": date.fromisoformat(fact["delisted_on"])}
             for fact in document["evidence"]["delisting_facts"]]
    result = run(db, facts, token, fetch_usage(token) if token else None, date.fromisoformat(args.start),
                 apply=args.apply, limit=args.limit)
    print(result)
    if not args.apply:
        print("[DRY-RUN] 未寫入，加 --apply 執行")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
