#!/usr/bin/env python3
"""國際指數每日同步 → intl_index。

台股最大 macro 缺口:原 macro_indicators 只抓台灣本地(利率/匯率/公債/M2)。
費半 SOX 是台股半導體/tech 領先指標(台股開盤前隔夜美股/費半漲跌高度預測 tech 方向)。

來源:FinMind USStockPrice(實測 ^SOX/^GSPC/^IXIC/^DJI/^VIX 皆可抓)。
存 intl_index:{index,name,date,close,open,high,low,chg_pct,source,updated_at},upsert by (index,date)。

用法: sync_intl_index.py [--days 10]
"""
import argparse
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
INDICES = {"^SOX": "費半", "^GSPC": "S&P500", "^IXIC": "那斯達克", "^DJI": "道瓊", "^VIX": "VIX恐慌"}


def fetch(sid, start):
    try:
        r = requests.get(API, params={"dataset": "USStockPrice", "data_id": sid,
                                      "start_date": start, "token": TOKEN}, timeout=30)
        return r.json().get("data", []) if r.status_code == 200 else []
    except requests.RequestException:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    args = ap.parse_args()
    if not TOKEN:
        raise SystemExit("no token")
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.intl_index
    col.create_index([("index", 1), ("date", 1)], unique=True)
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    tot = 0
    for sid, name in INDICES.items():
        rows = sorted(fetch(sid, start), key=lambda r: r.get("date", ""))
        ops = []
        prev_close = None
        for r in rows:
            d = r.get("date")
            close = r.get("Close")
            if not d or close is None:
                continue
            chg = round((close / prev_close - 1) * 100, 2) if prev_close else None
            doc = {"index": sid, "name": name,
                   "date": datetime.strptime(d[:10], "%Y-%m-%d"),
                   "close": close, "open": r.get("Open"), "high": r.get("High"),
                   "low": r.get("Low"), "chg_pct": chg,
                   "source": "FinMind:USStockPrice", "updated_at": datetime.now()}
            ops.append(UpdateOne({"index": sid, "date": doc["date"]}, {"$set": doc}, upsert=True))
            prev_close = close
        if ops:
            col.bulk_write(ops, ordered=False)
            tot += len(ops)
            last = rows[-1]
            print(f"  {sid}({name}): {len(ops)}筆, 最新 {last['date'][:10]} 收 {last.get('Close')}")
    print(f"\n完成:intl_index 寫入 {tot} 筆")


if __name__ == "__main__":
    main()
