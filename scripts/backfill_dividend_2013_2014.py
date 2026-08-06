#!/usr/bin/env python3
"""補 dividend_detail 2013–2014(讓早年價能正確還原)。

現況:2013-2014 除權息極缺(連 2330/2317 等權值股都 0 筆);FinMind TaiwanStockDividend
每檔有 2 筆。用與 sync_dividend_detail.py 完全一致的 snake_case 對映(build_adjustment_factors
讀的是 snake_case,若存 PascalCase 會算不出因子——backfill_dividend_gap.py 的坑)。

全股 4 碼,fetch 2013-01-01~2014-12-31,upsert(stock_id,date)$setOnInsert 純新增。
獨立 state,可 --resume。跑前暫停 hourly(佔 FinMind 配額)。
完成後跑:build_adjustment_factors.py --write → backfill_adj_close.py --execute --changed-only

用法: backfill_dividend_2013_2014.py [--sleep 5.8] [--resume] [--limit N]
"""
import argparse
import os
import re
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
STATE = "dividend_2013_2014_backfill_state"
START, END = "2013-01-01", "2014-12-31"


def to_num(v):
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def parse_year(y):
    m = re.search(r"\d+", str(y))
    return int(m.group()) if m else None


def api_to_db(rec):
    """與 sync_dividend_detail.api_to_db_record 一致的 snake_case 對映。"""
    yr = parse_year(rec.get("year", ""))
    return {
        "stock_id": rec.get("stock_id"),
        "date": rec.get("date"),
        "year": str(yr) if yr else rec.get("year", ""),
        "announcement_date": rec.get("AnnouncementDate", ""),
        "cash_ex_dividend_date": rec.get("CashExDividendTradingDate", ""),
        "cash_earnings_distribution": to_num(rec.get("CashEarningsDistribution")),
        "cash_statutory_surplus": to_num(rec.get("CashStatutorySurplus")),
        "stock_earnings_distribution": to_num(rec.get("StockEarningsDistribution")),
        "stock_statutory_surplus": to_num(rec.get("StockStatutorySurplus")),
        "stock_ex_dividend_date": rec.get("StockExDividendTradingDate", ""),
        "participate_distribution_shares": to_num(rec.get("ParticipateDistributionOfTotalShares")),
        "data_source": "FinMind:TaiwanStockDividend",
        "updated_at": datetime.now(),
    }


def fetch(sid, quota_wait=180, quota_max=25):
    """遇 402/429 配額用盡:等待重試(自癒),而非退出。
    連續等 quota_max 次(~75分)仍不行才放棄回 None。"""
    neterr = 0
    qtries = 0
    while True:
        try:
            r = requests.get(API, params={"dataset": "TaiwanStockDividend", "data_id": sid,
                                          "start_date": START, "end_date": END,
                                          "token": TOKEN}, timeout=45)
        except requests.RequestException:
            neterr += 1
            if neterr > 3:
                return []
            time.sleep(5 * neterr); continue
        if r.status_code in (402, 429):
            qtries += 1
            if qtries > quota_max:
                return None
            print(f"  {sid} 配額用盡,等 {quota_wait}s ({qtries}/{quota_max})", flush=True)
            time.sleep(quota_wait); continue
        if r.status_code != 200:
            return []
        return r.json().get("data", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=5.8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=99999)
    args = ap.parse_args()
    if not TOKEN:
        raise SystemExit("no token")
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    tg = sorted(s for s in db.stock_price.distinct("stock_id")
                if isinstance(s, str) and len(s) == 4 and s.isdigit())
    if args.resume:
        done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
        tg = [s for s in tg if s not in done]
    tg = tg[:args.limit]
    print(f"待補 {len(tg)} 檔 dividend {START}~{END}", flush=True)

    ins = 0
    for i, sid in enumerate(tg, 1):
        rows = fetch(sid)
        if rows is None:
            print(f"⚠️ 配額耗盡,已 {i-1}/{len(tg)},--resume 續跑", flush=True)
            break
        ops = []
        for rec in rows or []:
            doc = api_to_db(rec)
            doc["stock_id"] = doc["stock_id"] or sid
            if not doc.get("date"):
                continue
            ops.append(UpdateOne({"stock_id": doc["stock_id"], "date": doc["date"]},
                                 {"$setOnInsert": doc}, upsert=True))
        if ops:
            res = db.dividend_detail.bulk_write(ops, ordered=False)
            ins += res.upserted_count
        db[STATE].update_one({"stock_id": sid},
                             {"$set": {"rows": len(rows or []), "at": datetime.now()}},
                             upsert=True)
        if i % 50 == 0:
            print(f"  … {i}/{len(tg)}  新增 {ins:,} 筆", flush=True)
        time.sleep(args.sleep)

    print(f"\n完成:新增 {ins:,} 筆 dividend_detail", flush=True)
    print("⚠️ 接著跑 build_adjustment_factors.py --write 再 backfill_adj_close.py --execute --changed-only", flush=True)


if __name__ == "__main__":
    main()
