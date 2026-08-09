#!/usr/bin/env python3
"""補 stock_price 早年缺口(2013 起 → 各股現有起點之間所有洞)。

發現:早年極稀疏——2015 全池僅 159 檔,連 2330 都晚到 2016-02-15。若只補 2013-2014
會在 2015~2016 留新洞。故 start=2013-01-01 **不設 end**,靠 $setOnInsert 一次補滿
2013→現有起點所有缺日,完全不動既有列(既有列已存在→upsert no-op)。

沿用 backfill_price_history.py 的 schema/寫法:FinMind TaiwanStockPrice per-stock,
Decimal128, max→high / min→low / Trading_Volume→volume, date 午夜 naive datetime。
全池 4 碼(股票+ETF,排 6 碼權證);獨立 state。

⚠️ 佔 FinMind 配額(600/hr level-1),跑前暫停 hourly。可 --resume 續跑。
新列無 adj_* 欄位 → 完成後跑 backfill_adj_close.py --changed-only。

用法: backfill_price_2013_2014.py [--sleep 5.8] [--resume] [--limit N]
"""
import argparse
import os
import time
from datetime import datetime

import requests
from bson.decimal128 import Decimal128
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
STATE = "price_early_backfill_state"
START = "2013-01-01"   # 不設 end:補到各股現有起點,$setOnInsert 不動既有


def targets(db):
    """全池 4 碼(股票+ETF,排 6 碼權證)。2013-2014 未上市者 FinMind 回空,自動略過。"""
    return sorted(s for s in db.stock_price.distinct("stock_id")
                  if isinstance(s, str) and len(s) == 4 and s.isdigit())


def fetch(sid, retries=3):
    for i in range(retries):
        try:
            r = requests.get(API, params={"dataset": "TaiwanStockPrice", "data_id": sid,
                                          "start_date": START,
                                          "token": TOKEN}, timeout=90)
        except requests.RequestException:
            time.sleep(5 * (i + 1)); continue
        if r.status_code in (402, 429):
            return None
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    return []


def dec(v):
    return Decimal128(str(v)) if v is not None else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=5.8)   # 600/hr ≈ 6s/req
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=99999)
    args = ap.parse_args()
    if not TOKEN:
        raise SystemExit("no token")
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    tg = targets(db)
    if args.resume:
        done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
        tg = [s for s in tg if s not in done]
    tg = tg[:args.limit]
    print(f"待補 {len(tg)} 檔,start={START}(不設end,補到各股現有起點)", flush=True)

    ins = 0
    for i, sid in enumerate(tg, 1):
        rows = fetch(sid)
        if rows is None:
            print(f"⚠️ 配額耗盡,已 {i-1}/{len(tg)},--resume 續跑", flush=True)
            break
        ops = []
        for d in rows or []:
            try:
                dt = datetime.strptime(d["date"][:10], "%Y-%m-%d")
            except (KeyError, ValueError):
                continue
            ops.append(UpdateOne(
                {"stock_id": sid, "date": dt},
                {"$setOnInsert": {
                    "stock_id": sid, "symbol": sid, "date": dt,
                    "open": dec(d.get("open")), "high": dec(d.get("max")),
                    "low": dec(d.get("min")), "close": dec(d.get("close")),
                    "volume": dec(d.get("Trading_Volume")),
                    "Trading_Volume": dec(d.get("Trading_Volume")),
                    "Trading_money": d.get("Trading_money"),
                    "spread": d.get("spread"),
                    "data_source": "FinMind:TaiwanStockPrice",
                    "updated_at": datetime.now(),
                }}, upsert=True))
        if ops:
            res = db.stock_price.bulk_write(ops, ordered=False)
            ins += res.upserted_count
        db[STATE].update_one({"stock_id": sid},
                             {"$set": {"rows": len(rows or []), "at": datetime.now()}},
                             upsert=True)
        if i % 25 == 0:
            print(f"  … {i}/{len(tg)}  新增 {ins:,} 列", flush=True)
        time.sleep(args.sleep)

    print(f"\n完成:新增 {ins:,} 列", flush=True)
    print("⚠️ 新列無 adj_*,請跑 backfill_adj_close.py --execute --changed-only", flush=True)


if __name__ == "__main__":
    main()
