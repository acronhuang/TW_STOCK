#!/usr/bin/env python3
"""全市場每日股價下載器(per-date,上市 TWSE + 上櫃 TPEX)→ stock_price。

優於 FinMind 逐股:一請求 = 一天一市場全部股票,無 600/hr 硬配額(僅需禮貌延遲避反爬)。
大範圍歷史回填首選。實測 2013 起可用。

上市 TWSE: afterTrading/MI_INDEX?type=ALLBUT0999  日期=YYYYMMDD
  16欄 0代號 1名 2成交股數 3筆數 4成交金額 5開 6高 7低 8收 9漲跌 10價差 ...
上櫃 TPEX: www/zh-tw/afterTrading/dailyQuotes?type=AL  日期=YYYY/MM/DD(西元斜線,有吃日期)
  17欄 0代號 1名 2收 3漲跌 4開 5高 6低 7均價 8成交股數 9成交金額 10筆數 ...
  (舊 stk_quote_result.php 忽略日期恆回當日,勿用)

寫入與 FinMind schema 一致(Decimal128 OHLC),$setOnInsert 純新增(不動既有列),
date=午夜 naive datetime。只查 trading_dates 交易日,state 依 market 分開可 --resume。
新列無 adj_* → 需要則跑 backfill_adj_close.py --changed-only。

用法: market_perdate_price.py --from 2013-01-01 --to 2014-12-31 [--market both|twse|tpex] [--delay 4] [--resume]
"""
import argparse
import time
from datetime import datetime

import requests
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
STATE = "market_perdate_price_state"


def num(s):
    """'55,000'/'+2.45'→Decimal128;'--'/''/非數→None。"""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("+", "").strip()
    if t in ("", "--", "---", "X", "N/A"):
        return None
    try:
        return Decimal128(t)
    except Exception:
        return None


def money(s):
    return str(s).replace(",", "").strip() if s else None


def find_table(j):
    for t in j.get("tables", []):
        if t.get("data") and any("代號" in str(f) for f in t.get("fields", [])) and len(t["data"]) > 30:
            return t
    return None


def fetch(session, url, params, retries=4):
    """回傳個股表 dict / None(非交易日) / 'BLOCK'(反爬) / 'ERR'。"""
    for i in range(retries):
        try:
            r = session.get(url, params=params, headers={"User-Agent": UA}, timeout=40)
        except requests.RequestException:
            time.sleep(8 * (i + 1)); continue
        if r.status_code != 200:
            time.sleep(8 * (i + 1)); continue
        try:
            j = r.json()
        except ValueError:
            return "BLOCK"
        if str(j.get("stat", "")).upper() != "OK":
            return None
        return find_table(j)
    return "ERR"


# (col_open, col_high, col_low, col_close, col_vol, col_money)
TWSE_COLS = (5, 6, 7, 8, 2, 4)
TPEX_COLS = (4, 5, 6, 2, 8, 9)


def rows_to_ops(tbl, d, cols, source):
    co, ch, cl, cc, cv, cm = cols
    ops = []
    for row in tbl["data"]:
        if len(row) <= max(cols):
            continue
        code = str(row[0]).strip()
        close = num(row[cc])
        if not code or close is None:
            continue
        ops.append(UpdateOne(
            {"stock_id": code, "date": d},
            {"$setOnInsert": {
                "stock_id": code, "symbol": code, "date": d,
                "open": num(row[co]), "high": num(row[ch]),
                "low": num(row[cl]), "close": close,
                "volume": num(row[cv]), "Trading_Volume": num(row[cv]),
                "Trading_money": money(row[cm]),
                "data_source": source, "updated_at": datetime.now(),
            }}, upsert=True))
    return ops


def run_market(db, days, market, url, params_fn, cols, source, delay, resume):
    if resume:
        done = {r["_id"] for r in db[STATE].find({"_id": {"$regex": f"^{market}:"}}, {"_id": 1})}
        days = [d for d in days if f"{market}:{d:%Y-%m-%d}" not in done]
    print(f"[{market}] 待抓 {len(days)} 交易日", flush=True)
    session = requests.Session()
    ins = 0
    consec = 0
    for i, d in enumerate(days, 1):
        tbl = fetch(session, url, params_fn(d))
        if tbl in ("BLOCK", "ERR"):
            consec += 1
            print(f"  [{market}] {d:%Y-%m-%d}: {tbl}(反爬?)退避 {30*consec}s", flush=True)
            if consec >= 5:
                print(f"⛔ [{market}] 連續 5 次受阻,中止;冷卻後 --resume", flush=True)
                break
            time.sleep(30 * consec); continue
        consec = 0
        key = f"{market}:{d:%Y-%m-%d}"
        if tbl is None:
            db[STATE].update_one({"_id": key}, {"$set": {"rows": 0, "at": datetime.now()}}, upsert=True)
            time.sleep(delay); continue
        ops = rows_to_ops(tbl, d, cols, source)
        if ops:
            res = db.stock_price.bulk_write(ops, ordered=False)
            ins += res.upserted_count
        db[STATE].update_one({"_id": key}, {"$set": {"rows": len(ops), "at": datetime.now()}}, upsert=True)
        if i % 20 == 0:
            print(f"  [{market}] … {i}/{len(days)} ({d:%Y-%m}) 新增 {ins:,} 列", flush=True)
        time.sleep(delay)
    print(f"[{market}] 完成:新增 {ins:,} 列", flush=True)
    return ins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--market", choices=["both", "twse", "tpex"], default="both")
    ap.add_argument("--delay", type=float, default=4.0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    lo = datetime.strptime(args.frm, "%Y-%m-%d")
    hi = datetime.strptime(args.to, "%Y-%m-%d")
    days = sorted(datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
                  for r in db.trading_dates.find({}, {"date": 1, "_id": 0})
                  if len(str(r["date"])) >= 10
                  and lo <= datetime.strptime(str(r["date"])[:10], "%Y-%m-%d") <= hi)
    print(f"範圍 {args.frm}~{args.to},{len(days)} 交易日,market={args.market}", flush=True)

    total = 0
    if args.market in ("both", "twse"):
        total += run_market(db, days, "twse", TWSE_URL,
                            lambda d: {"date": d.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"},
                            TWSE_COLS, "TWSE:MI_INDEX", args.delay, args.resume)
    if args.market in ("both", "tpex"):
        total += run_market(db, days, "tpex", TPEX_URL,
                            lambda d: {"date": d.strftime("%Y/%m/%d"), "type": "AL", "response": "json", "id": ""},
                            TPEX_COLS, "TPEX:dailyQuotes", args.delay, args.resume)
    print(f"\n=== 全部完成:共新增 {total:,} 列 ===", flush=True)
    print("⚠️ 新列無 adj_*,需要則跑 backfill_adj_close.py --execute --changed-only", flush=True)


if __name__ == "__main__":
    main()
