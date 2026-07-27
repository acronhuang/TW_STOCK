#!/usr/bin/env python3
"""補融資融券餘額歷史 → margin_purchase_short_sale(新 snake schema)。

用 FinMind `TaiwanStockMarginPurchaseShortSale`(逐股全歷史,非 TWSE 反爬限制;
之前~40檔/日是舊下載只抓部分股)。每股一請求 range 查,寫新 schema,upsert by code+date。
--resume 跳過已有 <=2015 資料的股票。

用法: backfill_margin_finmind.py [--start 2013-01-01] [--delay 6] [--resume]
"""
import argparse
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
NO_STOP = {"債券ETF", "長期存股", "零成本", "零股"}

MAP = {
    "MarginPurchaseBuy": "margin_buy", "MarginPurchaseSell": "margin_sell",
    "MarginPurchaseCashRepayment": "margin_cash_repay",
    "MarginPurchaseTodayBalance": "margin_balance",
    "MarginPurchaseYesterdayBalance": "margin_prev_balance",
    "MarginPurchaseLimit": "margin_limit",
    "ShortSaleBuy": "short_buy", "ShortSaleSell": "short_sell",
    "ShortSaleCashRepayment": "short_cash_repay",
    "ShortSaleTodayBalance": "short_balance",
    "ShortSaleYesterdayBalance": "short_prev_balance",
    "ShortSaleLimit": "short_limit", "OffsetLoanAndShort": "offset",
}


def fetch(sid, start, retries=3):
    for i in range(retries):
        try:
            r = requests.get(API, params={"dataset": "TaiwanStockMarginPurchaseShortSale",
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
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--delay", type=float, default=6.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=99999)
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.margin_purchase_short_sale
    if not TOKEN:
        raise SystemExit("no token")

    from datetime import timedelta
    lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
    syms = sorted(s for s in db.stock_price.distinct("stock_id",
                  {"date": {"$gte": lat - timedelta(days=40)}})
                  if len(s) == 4 and not s.startswith("00"))
    if args.resume:
        cut = datetime(2015, 12, 31)
        done = set(col.distinct("code", {"source": "FinMind_margin", "date": {"$lte": cut}}))
        syms = [s for s in syms if s not in done]
    syms = syms[:args.limit]
    print(f"回填 {len(syms)} 檔 (FinMind margin, start={args.start})")
    tot = 0
    for i, sid in enumerate(syms, 1):
        rows = fetch(sid, args.start)
        if rows is None:
            print(f"⚠️ 配額耗盡,已 {i-1}/{len(syms)},--resume 續跑"); break
        ops = []
        for r in rows:
            d = r.get("date")
            if not d:
                continue
            doc = {"code": sid, "date": datetime.strptime(d[:10], "%Y-%m-%d"),
                   "name": r.get("symbol", ""), "source": "FinMind_margin",
                   "updated_at": datetime.now()}
            for fk, nk in MAP.items():
                if r.get(fk) is not None:
                    doc[nk] = r.get(fk)
            ops.append(UpdateOne({"code": sid, "date": doc["date"]}, {"$set": doc}, upsert=True))
        if ops:
            col.bulk_write(ops, ordered=False)
            tot += len(ops)
        if i % 100 == 0:
            print(f"  … {i}/{len(syms)} 累計 {tot:,} 筆")
        time.sleep(args.delay)
    col.create_index([("code", 1), ("date", 1)])
    print(f"\n完成:FinMind margin 寫入 {tot:,} 筆")


if __name__ == "__main__":
    main()
