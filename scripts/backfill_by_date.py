#!/usr/bin/env python3
"""
按日期回補 stock_price（自癒基礎件）。
與 twse_daily_update 不同：twse_daily_update 只抓「API 最新交易日」，本腳本可補**任意過去日期**——
用 TWSE MI_INDEX（上市）+ TPEX 新站台 otc（上櫃）的「按日期」端點。

用法:
  backfill_by_date.py --date 20260708            # dry-run，只報告
  backfill_by_date.py --date 20260708 --apply    # 實際 upsert
  backfill_by_date.py --date 20260708 --market twse|tpex|both   # 預設 both

TLS：兩個端點皆使用**正常憑證驗證**，請勿加回 `verify=False`。
原本帶有 `verify=False` + `urllib3.disable_warnings(...)`，2026-07-19 實測確認並無必要
（MI_INDEX 246KB、TPEX otc 3.9MB 皆 200 OK），已移除——那只是關掉中間人攻擊的防護，
換不到任何東西。若日後真的遇到憑證錯誤，正解是更新 CA 憑證庫，不是關驗證。
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_gap.codes import is_letter_etf, is_price_code  # noqa: E402



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
    r = requests.get(url, timeout=30)
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
        if not is_price_code(code):
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


def _tpex_roc(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y%m%d")
    return f"{dt.year}/{dt.month:02d}/{dt.day:02d}"


def parse_tpex_totals(payload: dict, date_str: str) -> dict:
    """dailyQuotes 的全日成交（含零股、盤後定價）。依欄名取值；狀態非 ok 或資料日不符回 {}。"""
    if str(payload.get("stat", "")).lower() != "ok" or payload.get("date") != date_str:
        return {}
    tables = payload.get("tables") or []
    if not tables:
        return {}
    names = [str(f).strip() for f in tables[0].get("fields") or []]
    try:
        i_vol, i_amt, i_trn = names.index("成交股數"), names.index("成交金額(元)"), names.index("成交筆數")
    except ValueError:
        return {}
    out = {}
    for row in tables[0].get("data") or []:
        try:
            volume = float(str(row[i_vol]).replace(",", "").strip())
        except ValueError:
            continue
        out[str(row[0]).strip()] = {"volume": volume, "amount": str(row[i_amt]).replace(",", "").strip(),
                                    "transaction": str(row[i_trn]).replace(",", "").strip()}
    return out


def fetch_tpex_totals(date_str: str) -> dict:
    r = requests.post("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes",
                      data={"date": _tpex_roc(date_str), "type": "EW", "id": "", "response": "json"},
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.tpex.org.tw/"}, timeout=60)
    r.raise_for_status()
    return parse_tpex_totals(r.json(), date_str)


def apply_totals(recs: list, totals: dict) -> list:
    """otc 端點只有整股盤（量被捨入到張）；有 dailyQuotes 的代號就換成全日量額筆數。"""
    for rec in recs:
        t = totals.get(rec["stock_id"])
        if t:
            rec["volume"] = Decimal128(str(t["volume"]))
            rec["amount"], rec["transaction"] = t["amount"], t["transaction"]
    return recs


def refresh_plan(docs: list, totals: dict) -> list[tuple[str, dict]]:
    """既有 TPEX_OTC 列中，量額筆數與全日值不同者 → [(stock_id, 要 $set 的欄位)]。不動價格與還原價。"""
    plan = []
    for doc in docs:
        t = totals.get(doc["stock_id"])
        if not t:
            continue
        current = doc.get("volume")
        current = float(current.to_decimal()) if hasattr(current, "to_decimal") else current
        if current == t["volume"] and str(doc.get("amount")) == t["amount"] and str(doc.get("transaction")) == t["transaction"]:
            continue
        plan.append((doc["stock_id"], {"volume": Decimal128(str(t["volume"])), "amount": t["amount"], "transaction": t["transaction"]}))
    return plan


def refresh_tpex_totals(date_str: str, apply: bool = False, db=None) -> dict:
    db = db or MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
    day = datetime.strptime(date_str, "%Y%m%d")
    totals = fetch_tpex_totals(date_str)
    docs = list(db.stock_price.find({"date": day, "data_source": "TPEX_OTC"}, {"stock_id": 1, "volume": 1, "amount": 1, "transaction": 1}))
    plan = refresh_plan(docs, totals) if totals else []
    if apply and plan:
        db.stock_price.bulk_write([UpdateOne({"stock_id": s, "date": day, "data_source": "TPEX_OTC"},
                                             {"$set": {**fields, "updated_at": datetime.now()}}) for s, fields in plan], ordered=False)
    return {"date": date_str, "otc_rows": len(docs), "totals": len(totals), "to_fix": len(plan), "applied": apply}


def fetch_tpex(date_str: str):
    """TPEX 新站台 otc 按日期。date_str=YYYYMMDD。回 list[doc]；量額筆數以 dailyQuotes 的全日值為準。"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    roc = f"{dt.year}/{dt.month:02d}/{dt.day:02d}"
    url = (f"https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
           f"?date={roc}&type=EW&response=json")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    rows = (r.json().get("tables") or [{}])[0].get("data") or []
    out = []
    for row in rows:
        if len(row) < 10:
            continue
        code = str(row[0]).strip()
        if not is_price_code(code):
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
    try:
        return apply_totals(out, fetch_tpex_totals(date_str))
    except Exception:  # noqa: BLE001 - dailyQuotes 暫時失敗時仍保留整股盤資料，由 --refresh-tpex-totals 事後修正
        return out


def upsert(db, recs):
    if not recs:
        return 0, 0
    ops = [UpdateOne({"stock_id": r["stock_id"], "date": r["date"]}, {"$set": r}, upsert=True)
           for r in recs]
    res = db.stock_price.bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count


def backfill_letter_etfs(db, start: str, end: str, apply: bool = False, twse=fetch_twse, tpex=fetch_tpex,
                         pause: float = 1.0) -> dict:
    """結尾帶字母的 ETF 區間回補。只新增缺的列（$setOnInsert），不改既有價格與還原價；來源失敗記錄後繼續。"""
    first, last = (datetime.strptime(v, "%Y%m%d").date().isoformat() for v in (start, end))
    days = sorted(row["date"] for row in db["trading_dates"].find({"date": {"$gte": first, "$lte": last}}, {"_id": 0, "date": 1}))
    operations, failures = [], []
    for day in days:
        compact = day.replace("-", "")
        for market, fetch in (("twse", twse), ("tpex", tpex)):
            try:
                found = fetch(compact)
            except Exception as exc:  # noqa: BLE001 - 單一來源失敗不中止整段回補
                failures.append({"date": day, "market": market, "error": str(exc)})
                continue
            operations += [UpdateOne({"stock_id": rec["stock_id"], "date": rec["date"]}, {"$setOnInsert": rec}, upsert=True)
                           for rec in found if is_letter_etf(rec["stock_id"])]
            time.sleep(pause)
    if apply and operations:
        db["stock_price"].bulk_write(operations, ordered=False)
    return {"days": len(days), "inserted_candidates": len(operations), "failures": failures, "applied": apply}


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
    ap.add_argument("--date", help="YYYYMMDD")
    ap.add_argument("--letter-etfs", nargs=2, metavar=("START", "END"),
                    help="只補結尾帶字母的 ETF 缺列（YYYYMMDD YYYYMMDD，含頭尾），不改既有列")
    ap.add_argument("--market", choices=["twse", "tpex", "both"], default="both")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--refresh-tpex-totals", action="store_true",
                    help="只把既有 TPEX_OTC 列的成交量/額/筆數改成全日值（含零股），不動價格")
    args = ap.parse_args()
    if args.letter_etfs:
        db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
        print(backfill_letter_etfs(db, *args.letter_etfs, apply=args.apply))
        return
    if not args.date:
        ap.error("--date 或 --letter-etfs 擇一")
    if args.refresh_tpex_totals:
        print(refresh_tpex_totals(args.date, args.apply))
        return
    res = run(args.date, args.market, args.apply)
    print(f"[{res['date']}] TWSE {res['twse']} + TPEX {res['tpex']} = {res['total']} 檔")
    if args.apply:
        print(f"  → 新增 {res['upserted']}  更新 {res['modified']}")
    else:
        print("  [DRY-RUN] 未寫入，加 --apply 執行")


if __name__ == "__main__":
    main()
