#!/usr/bin/env python3
"""補 quarterly_earnings.balance 的權益/股本 → 讓 pb_ratio 可算。

現況:quarterly_earnings.balance 只有資產/負債,缺 equity_parent/total_equity/capital_stock,
故 backfill_pe_pb_factors 算不出 BVPS → pb_ratio 近乎 0。
FinMind TaiwanStockBalanceSheet 有 Equity / EquityAttributableToOwnersOfParent / CapitalStock,
逐股抓、對映到 quarterly_earnings 的 {year,season},$set 進 balance 子文件。

FinMind 逐股 range 查(~2000請求)。遇 402/429 等待重試(自癒)。--resume 跳過已補。
完成後跑 backfill_pe_pb_factors.py。

用法: backfill_balance_equity.py [--start 2013-01-01] [--delay 5.8] [--resume]
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
STATE = "balance_equity_backfill_state"
# FinMind type → balance 欄位
MAP = {"EquityAttributableToOwnersOfParent": "equity_parent",
       "Equity": "total_equity", "CapitalStock": "capital_stock"}
Q = {3: 1, 6: 2, 9: 3, 12: 4}


def fetch(sid, start, quota_wait=180, quota_max=25):
    qt = neterr = 0
    while True:
        try:
            r = requests.get(API, params={"dataset": "TaiwanStockBalanceSheet", "data_id": sid,
                                          "start_date": start, "token": TOKEN}, timeout=60)
        except requests.RequestException:
            neterr += 1
            if neterr > 3:
                return []
            time.sleep(5 * neterr); continue
        if r.status_code in (402, 429):
            qt += 1
            if qt > quota_max:
                return None
            print(f"  {sid} 配額用盡,等{quota_wait}s ({qt}/{quota_max})", flush=True)
            time.sleep(quota_wait); continue
        if r.status_code != 200:
            return []
        return r.json().get("data", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--delay", type=float, default=5.8)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--limit", type=int, default=99999)
    args = ap.parse_args()
    if not TOKEN:
        raise SystemExit("no token")
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    qe = db.quarterly_earnings
    # 股票池 = quarterly_earnings 有的 symbol(這樣才對得上)
    syms = sorted(qe.distinct("symbol"))
    if args.resume:
        done = {r["_id"] for r in db[STATE].find({}, {"_id": 1})}
        syms = [s for s in syms if s not in done]
    syms = syms[:args.limit]
    print(f"補權益 {len(syms)} 檔 (FinMind BalanceSheet, start={args.start})", flush=True)

    upd = 0
    for i, sid in enumerate(syms, 1):
        rows = fetch(sid, args.start)
        if rows is None:
            print(f"⚠️ 配額耗盡,已 {i-1}/{len(syms)},--resume 續跑", flush=True); break
        # 依 date 聚合權益欄
        by_q = {}
        for r in rows or []:
            d = r.get("date"); ty = r.get("type"); v = r.get("value")
            if not d or ty not in MAP or v is None:
                continue
            dt = datetime.strptime(d[:10], "%Y-%m-%d")
            if dt.month not in Q:
                continue
            by_q.setdefault((dt.year, Q[dt.month]), {})[MAP[ty]] = v
        ops = []
        for (yr, sea), fields in by_q.items():
            setd = {f"balance.{k}": val for k, val in fields.items()}
            ops.append(UpdateOne({"symbol": sid, "year": yr, "season": sea},
                                 {"$set": setd}))
        if ops:
            res = qe.bulk_write(ops, ordered=False)
            upd += res.modified_count
        db[STATE].update_one({"_id": sid}, {"$set": {"n": len(by_q), "at": datetime.now()}}, upsert=True)
        if i % 100 == 0:
            print(f"  … {i}/{len(syms)}  更新 {upd:,} 季", flush=True)
        time.sleep(args.delay)
    print(f"\n完成:更新 {upd:,} 季的權益。接著跑 backfill_pe_pb_factors.py", flush=True)


if __name__ == "__main__":
    main()
