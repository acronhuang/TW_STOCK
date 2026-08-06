#!/usr/bin/env python3
"""補 monthly_revenue 的歷史缺口。

背景:`monthly_revenue` 來自 TWSE OpenAPI,而 TWSE 只供最近數月 ——
實測每檔中位數只有 4 期、909 檔 ≤3 期。而 `_has_recent_data` 判定
「最新日期 >= 今天就跳過」,所以每小時更新**永遠不會回補歷史**。

FinMind `TaiwanStockMonthRevenue` 有 79 個月(2020-01 起),用它補。

安全性:純新增。已存在的 (symbol, year_month) 完全不動 ——
用 $setOnInsert,既有的 TWSE 資料(含 name/industry 欄位)不會被覆寫。

yoy_growth / mom_growth 由本腳本從序列自行計算,因為 FinMind 只給原始營收。
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
TOKEN = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
STATE = "monthly_revenue_backfill_state"


def fetch(sid, start="2015-01-01"):
    r = requests.get(API, params={"dataset": "TaiwanStockMonthRevenue", "data_id": sid,
                                  "start_date": start, "token": TOKEN}, timeout=45)
    if r.status_code in (402, 429):
        return None                      # 配額耗盡
    if r.status_code != 200:
        return []
    return r.json().get("data", [])


def build(sid, rows):
    """FinMind 原始列 → monthly_revenue 形狀,並算出 mom / yoy"""
    by_ym = {}
    for d in rows:
        y, m = d.get("revenue_year"), d.get("revenue_month")
        rev = d.get("revenue")
        if not (y and m) or rev is None:
            continue
        by_ym[f"{int(y):04d}-{int(m):02d}"] = float(rev) / 1000  # 元→千元(對齊 sync_monthly_revenue/TWSE_OpenAPI;2026-08-01修:原本漏除,造成23.7萬列×1000)

    out = []
    for ym, rev in sorted(by_ym.items()):
        y, m = int(ym[:4]), int(ym[5:7])
        prev_m = f"{y:04d}-{m-1:02d}" if m > 1 else f"{y-1:04d}-12"
        prev_y = f"{y-1:04d}-{m:02d}"
        lm, ly = by_ym.get(prev_m), by_ym.get(prev_y)
        out.append({
            "symbol": sid, "year_month": ym, "revenue": rev,
            "last_month_revenue": lm, "last_year_revenue": ly,
            "mom_growth": ((rev / lm - 1) * 100) if lm else None,
            "yoy_growth": ((rev / ly - 1) * 100) if ly else None,
            "data_source": "FinMind:TaiwanStockMonthRevenue",
            "updated_at": datetime.now(),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=99999)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    col = db.monthly_revenue
    col.create_index([("symbol", 1), ("year_month", 1)], unique=True)

    lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
    from datetime import timedelta
    targets = sorted(
        s for s in db.stock_price.distinct("stock_id", {"date": {"$gte": lat - timedelta(days=40)}})
        if len(s) == 4 and not s.startswith("00"))
    if args.resume:
        done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
        targets = [s for s in targets if s not in done]
        print(f"續跑:已完成 {len(done)},剩 {len(targets)}", flush=True)
    targets = targets[:args.limit]
    print(f"待處理 {len(targets)} 檔", flush=True)

    ins = skipped = 0
    for i, sid in enumerate(targets, 1):
        rows = fetch(sid)
        if rows is None:
            print(f"⚠️ 配額耗盡,已處理 {i-1}/{len(targets)},可 --resume 續跑", flush=True)
            break
        docs = build(sid, rows or [])
        if docs:
            # $setOnInsert:既有 TWSE 資料一律不動,只補沒有的月份
            res = col.bulk_write([UpdateOne(
                {"symbol": d["symbol"], "year_month": d["year_month"]},
                {"$setOnInsert": d}, upsert=True) for d in docs], ordered=False)
            ins += res.upserted_count
            skipped += len(docs) - res.upserted_count
        db[STATE].update_one({"stock_id": sid},
                             {"$set": {"periods": len(docs), "at": datetime.now()}},
                             upsert=True)
        if i % 100 == 0:
            print(f"  … {i}/{len(targets)}  新增 {ins:,} 期(既有跳過 {skipped:,})", flush=True)
        time.sleep(args.sleep)

    print(f"\n完成:新增 {ins:,} 期,既有未動 {skipped:,} 期", flush=True)
    print(f"monthly_revenue 現況:{col.count_documents({}):,} 筆 / "
          f"{len(col.distinct('symbol'))} 檔", flush=True)


if __name__ == "__main__":
    main()
