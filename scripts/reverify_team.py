#!/usr/bin/env python3
"""
團隊分析復驗（reverify）
========================
兩層驗證，結果寫回 team_analysis 文件的 verify 欄位：

快層（預設，全市場、離線）：
  比對『分析當下用的收盤價』price_at_analysis vs stock_price 現時權威收盤。
  相符→fresh；不符→stale；任一缺→unknown。標記 verify.status/truth_close/checked_at。

慢層（--finmind N，抽查、線上、節流）：
  對 N 檔（優先 stale/unknown）打 FinMind TaiwanStockPrice 複核該日收盤，
  寫 verify.finmind={close, match, checked_at}。受 FinMind 額度限制，故抽樣。

用法:
  reverify_team.py --date 20260710              # 快層，單日
  reverify_team.py                              # 快層，全部日期
  reverify_team.py --date 20260710 --finmind 20 # 快層 + 對 20 檔 FinMind 複核
"""
import os
import sys
import time
from datetime import datetime

import requests
from bson import Decimal128
from pymongo import UpdateOne

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from dotenv import load_dotenv

load_dotenv("/home/mdsadmin/Stock/tw-stock-analysis/.env")
from src.moe.team_store import get_db

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.getenv("FINMIND_API_TOKEN", "")
TOL = 0.005  # 收盤價相對容差

ARGS = sys.argv[1:]
DATE = ARGS[ARGS.index("--date") + 1] if "--date" in ARGS else None
FINMIND_N = int(ARGS[ARGS.index("--finmind") + 1]) if "--finmind" in ARGS else 0


def tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def close_match(a, b):
    if a is None or b is None:
        return None
    return abs(a - b) <= max(TOL, abs(b) * TOL)


def _ref_date(price, run_date):
    """執行日當時最新的交易日 = stock_price 中 <=run_date、非 TAIEX 的最大日期。
    分析用的是這一天的收盤（07-10 執行 → 基準 07-09）。"""
    doc = price.find_one({"date": {"$lte": run_date}, "symbol": {"$ne": "TAIEX"}},
                         {"date": 1}, sort=[("date", -1)])
    return doc["date"] if doc else None


def fast_layer(db, date_filter):
    col = db["team_analysis"]
    price = db["stock_price"]
    docs = list(col.find(date_filter, {"symbol": 1, "date": 1, "price_at_analysis": 1}))
    # 每個執行日對應一個「基準交易日」，truth = 該基準日各股收盤
    truth = {}
    for run_date in {x["date"] for x in docs}:
        ref = _ref_date(price, run_date)
        if ref is None:
            continue
        for p in price.find({"date": ref}, {"symbol": 1, "close": 1}):
            truth[(p["symbol"], run_date)] = tof(p.get("close"))
    now = datetime.now()
    ops, cnt = [], {"fresh": 0, "stale": 0, "unknown": 0}
    for x in docs:
        seen = x.get("price_at_analysis")
        real = truth.get((x["symbol"], x["date"]))
        m = close_match(seen, real)
        status = "unknown" if m is None else ("fresh" if m else "stale")
        cnt[status] += 1
        ops.append(UpdateOne({"_id": x["_id"]}, {"$set": {
            "verify.status": status, "verify.truth_close": real,
            "verify.checked_at": now}}))
    if ops:
        col.bulk_write(ops, ordered=False)
    return cnt, docs


def finmind_close(symbol, ref_date):
    """FinMind 上 ref_date 當日收盤。回 None=無回應；0.0 也視為無交易(回 None)。"""
    try:
        ds = ref_date.strftime("%Y-%m-%d")
        r = requests.get(FINMIND_URL, params={
            "dataset": "TaiwanStockPrice", "data_id": symbol,
            "start_date": ds, "end_date": ds, "token": FINMIND_TOKEN,
        }, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        row = next((d for d in data if str(d.get("date")) == ds), None)  # 僅採 ref_date 當日
        c = tof(row.get("close")) if row else None
        return c if c else None   # 0.0/None → None（無交易）
    except Exception:
        return None


def slow_layer(db, date_filter, n):
    col = db["team_analysis"]
    price = db["stock_price"]
    # 慢層目的：外部複核『DB 權威收盤 truth_close 是否被 FinMind 證實』。
    # 只有 truth_close 存在(=fresh/DB有資料)的標的才可比對，故優先抽這些；
    # truth_close 為 None(unknown/DB無資料)無從比對，另計「DB無資料」而非誤判為背離。
    proj = {"symbol": 1, "date": 1, "verify.truth_close": 1, "verify.status": 1}
    q = dict(date_filter)
    cand = list(col.find({**q, "verify.truth_close": {"$ne": None}}, proj).limit(n))
    if len(cand) < n:
        cand += list(col.find({**q, "verify.truth_close": None}, proj).limit(n - len(cand)))
    ref_cache = {}
    now = datetime.now()
    match, mism, noresp, no_db = 0, 0, 0, 0
    for x in cand:
        rd = ref_cache.get(x["date"]) or _ref_date(price, x["date"])
        ref_cache[x["date"]] = rd
        db_close = (x.get("verify") or {}).get("truth_close")
        if db_close is None:            # DB 本身無此日收盤 → 無從複核
            no_db += 1
            col.update_one({"_id": x["_id"]}, {"$set": {"verify.finmind": {
                "finmind_close": None, "db_close": None, "match": None,
                "note": "DB無資料", "ref_date": rd, "checked_at": now}}})
            continue
        fc = finmind_close(x["symbol"], rd) if rd else None
        m = close_match(db_close, fc)   # DB 權威收盤 vs FinMind
        if fc is None:
            noresp += 1
        elif m:
            match += 1
        else:
            mism += 1
        col.update_one({"_id": x["_id"]}, {"$set": {"verify.finmind": {
            "finmind_close": fc, "db_close": db_close, "match": m,
            "ref_date": rd, "checked_at": now}}})
        time.sleep(0.4)  # FinMind 節流
    return {"抽查": len(cand), "DB獲證實": match, "背離": mism,
            "FinMind無回應": noresp, "DB無資料(未列入比對)": no_db}


def main():
    db = get_db()
    date_filter = {}
    if DATE:
        date_filter["date"] = datetime.strptime(DATE, "%Y%m%d")
    label = DATE or "全部日期"

    cnt, docs = fast_layer(db, date_filter)
    print(f"== 快層復驗 [{label}] ==")
    print(f"  文件 {len(docs)}  → fresh {cnt['fresh']}  stale {cnt['stale']}  unknown {cnt['unknown']}")

    if FINMIND_N > 0:
        if not FINMIND_TOKEN:
            print("  ⚠️ 無 FINMIND_API_TOKEN，跳過慢層")
        else:
            res = slow_layer(db, date_filter, FINMIND_N)
            print(f"== 慢層 FinMind 抽查 ==")
            print("  " + "  ".join(f"{k}={v}" for k, v in res.items()))


if __name__ == "__main__":
    main()
