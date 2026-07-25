#!/usr/bin/env python3
"""補股價歷史缺口。

2026-07-20 查證:361 檔普通股的行情實質上只從 2022 起,但其中
**149 檔在 2022 前有除權息紀錄** —— 能配息代表當時已公開發行並在市場交易,
所以那是資料沒收到,不是後來才上市(例:2883 開發金是老牌金控)。

後果:任何跨 2016~2021 的回測,這些股票等於不存在 —— 選樣偏誤。
另外它們也讓除權息係數算錯(bisect 抓到跨年的錯誤鄰居,已另加防呆)。

純新增:用 $setOnInsert,既有的價格列一律不動。
補進來的列不含 adj_* 欄位,交由 backfill_adj_close --changed-only 統一處理
(它的增量條件涵蓋「有任何一列 adjustment_factor 為 None」)。
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
STATE = "price_history_backfill_state"


def targets(db):
    """行情實質起始 >= 2022,且 2022 前有除權息紀錄 → 確定當時已上市"""
    rows = db.stock_price.aggregate([
        {"$group": {"_id": {"s": "$stock_id", "y": {"$year": "$date"}}, "n": {"$sum": 1}}}])
    by = {}
    for r in rows:
        by.setdefault(r["_id"]["s"], {})[r["_id"]["y"]] = r["n"]

    out = []
    for s, ys in by.items():
        if len(s) != 4 or s.startswith("00"):
            continue
        real = [y for y, n in ys.items() if n >= 100]
        if not real or min(real) < 2022:
            continue
        if db.dividend_detail.count_documents(
                {"stock_id": s, "cash_ex_dividend_date": {"$lt": "2022-01-01", "$ne": ""}}):
            out.append(s)
    return sorted(out)


def fetch(sid, start="2015-01-01"):
    r = requests.get(API, params={"dataset": "TaiwanStockPrice", "data_id": sid,
                                  "start_date": start, "token": TOKEN}, timeout=60)
    if r.status_code in (402, 429):
        return None
    if r.status_code != 200:
        return []
    return r.json().get("data", [])


def dec(v):
    return Decimal128(str(v)) if v is not None else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=99999)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    tg = targets(db)
    if args.resume:
        done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
        tg = [s for s in tg if s not in done]
    tg = tg[:args.limit]
    print(f"待補 {len(tg)} 檔(確定當時已上市但缺行情)", flush=True)

    ins = 0
    for i, sid in enumerate(tg, 1):
        rows = fetch(sid)
        if rows is None:
            print(f"⚠️ 配額耗盡,已處理 {i-1}/{len(tg)},可 --resume", flush=True)
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
    print("⚠️ 新列尚無 adj_* 欄位,請跑 backfill_adj_close.py --execute --changed-only", flush=True)


if __name__ == "__main__":
    main()
