#!/usr/bin/env python3
"""補齊 dividend_detail 缺口。

sync_dividend_detail.py 的抓取範圍寫死為 stock_factors.dividend_yield>0,
而 TWSE 殖利率只算現金股利 → 只配股票股利的公司永遠進不了名單。
本腳本改以「近期仍在交易的 4 碼普通股」為母體,補抓缺漏者。純新增,不覆寫既有文件。
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_TOKEN") or os.getenv("FINMIND_API_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"

DEC = ("cash_earnings_distribution", "stock_earnings_distribution",
       "cash_statutory_surplus", "stock_statutory_surplus",
       "cash_increase_subscription_rate", "cash_increase_subscription_price",
       "participate_distribution_shares", "total_employee_stock_dividend",
       "total_employee_cash_dividend", "director_remuneration")


def targets(db):
    lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
    since = lat - timedelta(days=40)
    active = {s for s in db.stock_price.distinct("stock_id", {"date": {"$gte": since}})
              if len(s) == 4 and not s.startswith("00")}
    have = set(db.dividend_detail.distinct("stock_id"))
    return sorted(active - have)


def fetch(sym):
    r = requests.get(API, params={"dataset": "TaiwanStockDividend", "data_id": sym,
                                  "start_date": "2010-01-01", "token": TOKEN}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
    return r.json().get("data", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    syms = targets(db)[:args.limit]
    print(f"缺口股票 {len(syms)} 檔{'(dry-run)' if args.dry_run else ''}")
    if not TOKEN:
        sys.exit("FINMIND_TOKEN 未設定")

    stat = {"no_data": 0, "with_data": 0, "inserted": 0, "dup": 0, "err": 0}
    found = []
    for i, sym in enumerate(syms, 1):
        try:
            data = fetch(sym)
        except Exception as e:
            stat["err"] += 1
            print(f"  ! {sym} {e}")
            time.sleep(2)
            continue

        if not data:
            stat["no_data"] += 1
        else:
            stat["with_data"] += 1
            found.append((sym, len(data)))
            if not args.dry_run:
                for rec in data:
                    doc = dict(rec)
                    doc["stock_id"] = doc.get("stock_id") or sym
                    doc["updated_at"] = datetime.now()
                    doc["data_source"] = "FinMind:TaiwanStockDividend"
                    res = db.dividend_detail.update_one(
                        {"stock_id": doc["stock_id"], "date": doc["date"]},
                        {"$setOnInsert": doc}, upsert=True)
                    if res.upserted_id:
                        stat["inserted"] += 1
                    else:
                        stat["dup"] += 1
        if i % 50 == 0:
            print(f"  … {i}/{len(syms)}  {stat}")
        time.sleep(0.2)

    print(f"\n完成: {stat}")
    print(f"實際有除權息歷史的: {len(found)} 檔 / 查詢 {len(syms)} 檔")
    for s, n in sorted(found, key=lambda x: -x[1])[:25]:
        print(f"   {s}: {n} 筆")


if __name__ == "__main__":
    main()
