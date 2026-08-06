#!/usr/bin/env python3
"""TWSE 每日全股股價下載器(per-date,上市)→ stock_price。

優於 FinMind 逐股:MI_INDEX 一請求 = 一天全部上市股 OHLCV,無 600/hr 硬配額
(只需禮貌延遲避反爬)。大範圍歷史回填首選。實測 2013 起可用。

來源: https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999
  tables 中 title 含「每日收盤行情」那張為個股表,16 欄:
  0證券代號 1名稱 2成交股數 3成交筆數 4成交金額 5開 6高 7低 8收 9漲跌(+/-) 10漲跌價差 ...
type=ALLBUT0999 已排除權證/牛熊證。只上市(上櫃需 TPEX 對應端點,另寫)。

寫入與 FinMind schema 一致(Decimal128 OHLC),$setOnInsert 純新增(不動既有列),
date=午夜 naive datetime,data_source="TWSE:MI_INDEX"。只查 trading_dates 交易日,可 --resume。
新列無 adj_* → 完成後跑 backfill_adj_close.py --changed-only。

用法: twse_perdate_price.py --from 2013-01-01 --to 2014-12-31 [--delay 4] [--resume]
"""
import argparse
import time
from datetime import datetime, timedelta

import requests
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
STATE = "twse_perdate_price_state"


def num(s):
    """'55,000'→Decimal128;'--'/''/非數→None(保留 '0.00')。"""
    if s is None:
        return None
    t = str(s).replace(",", "").strip()
    if t in ("", "--", "---", "X", "N/A"):
        return None
    try:
        return Decimal128(t)
    except Exception:
        return None


def find_stock_table(j):
    for t in j.get("tables", []):
        fields = t.get("fields", [])
        if t.get("data") and any("代號" in str(f) for f in fields) and len(t["data"]) > 30:
            return t
    return None


def fetch_day(session, d, retries=4):
    for i in range(retries):
        try:
            r = session.get(URL, params={"date": d.strftime("%Y%m%d"),
                                         "type": "ALLBUT0999", "response": "json"},
                            headers={"User-Agent": UA}, timeout=40)
        except requests.RequestException:
            time.sleep(8 * (i + 1)); continue
        if r.status_code != 200:
            time.sleep(8 * (i + 1)); continue
        try:
            j = r.json()
        except ValueError:
            return "BLOCK"   # 反爬常回非 JSON
        if j.get("stat") != "OK":
            return None      # 非交易日/無資料
        return find_stock_table(j)
    return "ERR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    lo = datetime.strptime(args.frm, "%Y-%m-%d")
    hi = datetime.strptime(args.to, "%Y-%m-%d")

    # 只查 trading_dates 交易日(字串 date)
    days = sorted(datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
                  for r in db.trading_dates.find({}, {"date": 1, "_id": 0})
                  if len(str(r["date"])) >= 10
                  and lo <= datetime.strptime(str(r["date"])[:10], "%Y-%m-%d") <= hi)
    if args.resume:
        done = {r["_id"] for r in db[STATE].find({}, {"_id": 1})}
        days = [d for d in days if d.strftime("%Y-%m-%d") not in done]
    print(f"待抓 {len(days)} 交易日 {args.frm}~{args.to}(TWSE per-date)", flush=True)

    session = requests.Session()
    ins = 0
    consec_block = 0
    for i, d in enumerate(days, 1):
        tbl = fetch_day(session, d)
        if tbl in ("BLOCK", "ERR"):
            consec_block += 1
            print(f"  {d:%Y-%m-%d}: {tbl}(反爬?),退避 {30*consec_block}s", flush=True)
            if consec_block >= 5:
                print("⛔ 連續 5 次受阻,中止;冷卻後 --resume 續跑", flush=True)
                break
            time.sleep(30 * consec_block)
            continue
        consec_block = 0
        if tbl is None:
            # 非交易日(日曆誤列)→ 記 state 跳過
            db[STATE].update_one({"_id": d.strftime("%Y-%m-%d")},
                                 {"$set": {"rows": 0, "at": datetime.now()}}, upsert=True)
            time.sleep(args.delay); continue
        ops = []
        for row in tbl["data"]:
            code = str(row[0]).strip()
            close = num(row[8])
            if not code or close is None:
                continue
            ops.append(UpdateOne(
                {"stock_id": code, "date": d},
                {"$setOnInsert": {
                    "stock_id": code, "symbol": code, "date": d,
                    "open": num(row[5]), "high": num(row[6]),
                    "low": num(row[7]), "close": close,
                    "volume": num(row[2]), "Trading_Volume": num(row[2]),
                    "Trading_money": (str(row[4]).replace(",", "") if row[4] else None),
                    "data_source": "TWSE:MI_INDEX", "updated_at": datetime.now(),
                }}, upsert=True))
        if ops:
            res = db.stock_price.bulk_write(ops, ordered=False)
            ins += res.upserted_count
        db[STATE].update_one({"_id": d.strftime("%Y-%m-%d")},
                             {"$set": {"rows": len(ops), "at": datetime.now()}}, upsert=True)
        if i % 20 == 0:
            print(f"  … {i}/{len(days)} ({d:%Y-%m})  新增 {ins:,} 列", flush=True)
        time.sleep(args.delay)

    print(f"\n完成:TWSE per-date 新增 {ins:,} 列", flush=True)
    print("⚠️ 新列無 adj_*,需要則跑 backfill_adj_close.py --execute --changed-only", flush=True)


if __name__ == "__main__":
    main()
