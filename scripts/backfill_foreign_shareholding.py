#!/usr/bin/env python3
"""外資持股回填 + 每日更新 → foreign_shareholding(datetime date)。

用 FinMind `TaiwanStockShareholding`(外資及陸資持股比例,逐股全歷史 2015+)。
原 foreign_shareholding 是孤兒(無寫入者、只2025-02~2026-02、date曾為字串已修)。
本 script 補歷史 + 可每日跑更新。date 寫 datetime,upsert by stock_id+date。

⚠️ 用 FinMind 配額,勿與其他 FinMind 回填同時跑。
用法: backfill_foreign_shareholding.py [--start 2015-01-01] [--delay 6] [--resume] [--daily]
"""
import argparse
import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"

KEEP = ["stock_name", "InternationalCode", "ForeignInvestmentRemainingShares",
        "ForeignInvestmentShares", "ForeignInvestmentRemainRatio",
        "ForeignInvestmentSharesRatio", "ForeignInvestmentUpperLimitRatio",
        "ChineseInvestmentUpperLimitRatio", "NumberOfSharesIssued",
        "RecentlyDeclareDate", "note"]


def fetch(sid, start, retries=3):
    for i in range(retries):
        try:
            r = requests.get(API, params={"dataset": "TaiwanStockShareholding",
                                          "data_id": sid, "start_date": start, "token": TOKEN}, timeout=45)
        except requests.RequestException:
            time.sleep(5 * (i + 1)); continue
        if r.status_code == 200:
            return r.json().get("data", [])
        if r.status_code in (402, 429):
            return None
        time.sleep(3 * (i + 1))
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--delay", type=float, default=6.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--daily", action="store_true", help="只抓近30天(每日cron用)")
    ap.add_argument("--limit", type=int, default=99999)
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.foreign_shareholding
    if not TOKEN:
        raise SystemExit("no token")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d") if args.daily else args.start

    lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
    syms = sorted(s for s in db.stock_price.distinct("stock_id",
                  {"date": {"$gte": lat - timedelta(days=40)}})
                  if len(s) == 4 and not s.startswith("00"))
    if args.resume and not args.daily:
        done = set(col.distinct("stock_id", {"date": {"$lte": datetime(2015, 12, 31)}}))
        syms = [s for s in syms if s not in done]
    syms = syms[:args.limit]
    print(f"外資持股回填 {len(syms)} 檔 (start={start}{' daily' if args.daily else ''})")
    tot = 0
    for i, sid in enumerate(syms, 1):
        rows = fetch(sid, start)
        if rows is None:
            print(f"⚠️ 配額耗盡,已 {i-1}/{len(syms)},--resume 續跑"); break
        ops = []
        for r in rows:
            d = r.get("date")
            if not d:
                continue
            doc = {"stock_id": sid, "date": datetime.strptime(d[:10], "%Y-%m-%d"),
                   "source": "FinMind_shareholding", "updated_at": datetime.now()}
            for k in KEEP:
                if r.get(k) is not None:
                    doc[k] = r.get(k)
            ops.append(UpdateOne({"stock_id": sid, "date": doc["date"]}, {"$set": doc}, upsert=True))
        if ops:
            col.bulk_write(ops, ordered=False)
            tot += len(ops)
        if i % 100 == 0:
            print(f"  … {i}/{len(syms)} 累計 {tot:,} 筆")
        time.sleep(args.delay)
    col.create_index([("stock_id", 1), ("date", 1)])
    col.create_index([("date", 1)])
    print(f"\n完成:foreign_shareholding 寫入 {tot:,} 筆")


if __name__ == "__main__":
    main()
