#!/usr/bin/env python3
"""
按日期回補 stock_price（自癒基礎件）。
與 twse_daily_update 不同：twse_daily_update 只抓「API 最新交易日」，本腳本可補**任意過去日期**——
用 TWSE MI_INDEX（上市）+ TPEX 新站台 otc（上櫃）的「按日期」端點。

用法:
  backfill_by_date.py --date 20260708            # dry-run，只報告
  backfill_by_date.py --date 20260708 --apply    # 實際 upsert
  backfill_by_date.py --date 20260708 --market twse|tpex|both   # 預設 both
"""
import argparse
import sys
from datetime import datetime

import requests
import urllib3
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _to_dec(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("+", "").strip()
    if s in ("", "--", "N/A", "---", "-"):
        return None
    try:
        f = float(s)
        return Decimal128(str(f)) if f != 0 else None
    except (ValueError, TypeError):
        return None


def fetch_twse(date_str: str):
    """TWSE MI_INDEX 按日期。date_str=YYYYMMDD。回 list[doc]。"""
    url = (f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
           f"?response=json&date={date_str}&type=ALLBUT0999")
    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    raw = r.json()
    if raw.get("stat") != "OK":
        return []
    tables = raw.get("tables", [])
    data_table = next((t for t in tables if "個股" in t.get("title", "") and "日成交" in t.get("title", "")), None)
    if not data_table:
        data_table = max(tables, key=lambda t: len(t.get("data", [])), default=None)
    if not data_table or not data_table.get("data"):
        return []
    dt = datetime.strptime(date_str, "%Y%m%d")
    out = []
    for row in data_table["data"]:
        if len(row) < 10:
            continue
        code = str(row[0]).strip()
        if not code.isdigit():
            continue
        close = _to_dec(row[8])
        if close is None:
            continue
        # MI_INDEX: 0代號 1名稱 2成交股數 3成交筆數 4成交金額 5開 6高 7低 8收
        out.append({
            "stock_id": code, "symbol": code, "date": dt,
            "open": _to_dec(row[5]), "high": _to_dec(row[6]), "low": _to_dec(row[7]),
            "close": close, "adj_close": close, "volume": _to_dec(row[2]),
            "amount": str(row[4]).replace(",", "").strip(),         # 成交金額(供均額因子)
            "transaction": str(row[3]).replace(",", "").strip(),     # 成交筆數
            "name": str(row[1]).strip(), "data_source": "TWSE_MI_INDEX",
            "updated_at": datetime.now(),
        })
    return out


def fetch_tpex(date_str: str):
    """TPEX 新站台 otc 按日期。date_str=YYYYMMDD。回 list[doc]。"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    roc = f"{dt.year}/{dt.month:02d}/{dt.day:02d}"
    url = (f"https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
           f"?date={roc}&type=EW&response=json")
    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    rows = (r.json().get("tables") or [{}])[0].get("data") or []
    out = []
    for row in rows:
        if len(row) < 10:
            continue
        code = str(row[0]).strip()
        if not code.isdigit():
            continue
        close = _to_dec(row[2])
        if close is None:
            continue
        # otc EW: 0代號 1名稱 2收 4開 5高 6低 7成交股數 8成交金額 9成交筆數
        out.append({
            "stock_id": code, "symbol": code, "date": dt,
            "open": _to_dec(row[4]), "high": _to_dec(row[5]), "low": _to_dec(row[6]),
            "close": close, "adj_close": close, "volume": _to_dec(row[7]),
            "amount": str(row[8]).replace(",", "").strip(),         # 成交金額(供均額因子)
            "transaction": str(row[9]).replace(",", "").strip(),     # 成交筆數
            "name": str(row[1]).strip(), "data_source": "TPEX_OTC",
            "updated_at": datetime.now(),
        })
    return out


def upsert(db, recs):
    if not recs:
        return 0, 0
    ops = [UpdateOne({"stock_id": r["stock_id"], "date": r["date"]}, {"$set": r}, upsert=True)
           for r in recs]
    res = db.stock_price.bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count


def run(date_str: str, market: str = "both", apply: bool = False,
        db=None) -> dict:
    """程式化入口（供 --heal 呼叫）。回 {twse, tpex, upserted, modified, applied}。"""
    db = db or MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
    recs = []
    n_twse = n_tpex = 0
    if market in ("both", "twse"):
        t = fetch_twse(date_str); n_twse = len(t); recs += t
    if market in ("both", "tpex"):
        p = fetch_tpex(date_str); n_tpex = len(p); recs += p
    up = mod = 0
    if apply:
        up, mod = upsert(db, recs)
    return {"date": date_str, "twse": n_twse, "tpex": n_tpex,
            "total": len(recs), "upserted": up, "modified": mod, "applied": apply}


def main():
    ap = argparse.ArgumentParser(description="按日期回補 stock_price")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    ap.add_argument("--market", choices=["twse", "tpex", "both"], default="both")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    res = run(args.date, args.market, args.apply)
    print(f"[{res['date']}] TWSE {res['twse']} + TPEX {res['tpex']} = {res['total']} 檔")
    if args.apply:
        print(f"  → 新增 {res['upserted']}  更新 {res['modified']}")
    else:
        print("  [DRY-RUN] 未寫入，加 --apply 執行")


if __name__ == "__main__":
    main()
