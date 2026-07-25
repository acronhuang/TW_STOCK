#!/usr/bin/env python3
"""
按日期回補 margin_purchase_short_sale（融資融券餘額）。

與 twse_openapi_sync.sync_margin_trading 的差異：那支用 OpenAPI `/exchangeReport/MI_MARGN`，
**只給最新交易日**；本腳本用 TWSE RWD 的按日期端點，可補任意過去日。同 backfill_by_date.py
之於 stock_price 的關係。

緣起：2026-07-19 完整性檢查（改用 trading_dates 外部錨後）首次發現 2026-02-23~04-01 共 27 個
交易日完全無資料。該段原被 find_gaps 的 `tmin = min(date型別日期)` 邏輯排除在檢查外
——因為更早的資料當時是「字串型別 date」，不列入 tmin 計算。

寫入 schema 對齊 sync_margin_trading 的**新 schema**（code/margin_*/short_*），
非舊 FinMind schema（stock_id/MarginPurchase*）。本表兩套 schema 並存是已知技術債，
消費端 chip_score_scan.py 已同時處理兩者。

用法:
  backfill_margin_by_date.py --date 20260223              # dry-run
  backfill_margin_by_date.py --date 20260223 --apply
  backfill_margin_by_date.py --from 20260223 --to 20260401 --apply   # 區間（自動跳過非交易日）
"""
import argparse
import time
from datetime import datetime

import requests
from pymongo import ASCENDING, MongoClient

URL = ("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
       "?response=json&date={d}&selectType=ALL")


def _int(v):
    """'1,017' → 1017；'--'/空 → 0。"""
    s = str(v).replace(",", "").strip()
    if s in ("", "--", "---", "N/A"):
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def fetch(date_str: str):
    """回 list[doc]。查無資料（非交易日/未公布）回 []。"""
    r = requests.get(URL.format(d=date_str), timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "OK":
        return []
    # 個股明細在「融資融券彙總」那張表；用欄位數 16 + 筆數最多來認，避免標題文字變動就抓不到
    tbl = None
    for t in j.get("tables", []):
        if len(t.get("fields") or []) == 16 and t.get("data"):
            tbl = t if (tbl is None or len(t["data"]) > len(tbl["data"])) else tbl
    if not tbl:
        return []
    day = datetime.strptime(date_str, "%Y%m%d")
    out = []
    for row in tbl["data"]:
        if len(row) < 16:
            continue
        code = str(row[0]).strip()
        if not code or not code[0].isdigit():
            continue
        out.append({
            "code": code, "name": str(row[1]).strip(), "date": day,
            "margin_buy": _int(row[2]), "margin_sell": _int(row[3]),
            "margin_cash_repay": _int(row[4]), "margin_prev_balance": _int(row[5]),
            "margin_balance": _int(row[6]), "margin_limit": _int(row[7]),
            "short_buy": _int(row[8]), "short_sell": _int(row[9]),
            "short_cash_repay": _int(row[10]), "short_prev_balance": _int(row[11]),
            "short_balance": _int(row[12]), "short_limit": _int(row[13]),
            "offset": _int(row[14]), "note": str(row[15]).strip(),
            "updated_at": datetime.now(),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="按日期回補融資融券")
    ap.add_argument("--date", help="單日 YYYYMMDD")
    ap.add_argument("--from", dest="d_from", help="區間起 YYYYMMDD")
    ap.add_argument("--to", dest="d_to", help="區間迄 YYYYMMDD")
    ap.add_argument("--apply", action="store_true", help="實際寫入（預設 dry-run）")
    ap.add_argument("--db-uri", default="mongodb://localhost:27017")
    ap.add_argument("--sleep", type=float, default=1.5, help="每次請求間隔秒（禮貌對待 TWSE）")
    args = ap.parse_args()

    db = MongoClient(args.db_uri)["tw_stock_analysis"]
    col = db["margin_purchase_short_sale"]
    col.create_index([("code", ASCENDING), ("date", ASCENDING)])

    if args.date:
        days = [args.date]
    elif args.d_from and args.d_to:
        # 只跑 trading_dates 認定的交易日，避免對非交易日發無謂請求
        lo = f"{args.d_from[:4]}-{args.d_from[4:6]}-{args.d_from[6:]}"
        hi = f"{args.d_to[:4]}-{args.d_to[4:6]}-{args.d_to[6:]}"
        days = [d["date"].replace("-", "") for d in
                db.trading_dates.find({"date": {"$gte": lo, "$lte": hi}}).sort("date", 1)]
    else:
        ap.error("需指定 --date 或 --from/--to")

    print(f"目標 {len(days)} 個交易日{'（實際寫入）' if args.apply else '（DRY-RUN）'}")
    tot_new = tot_upd = tot_empty = 0
    for i, d in enumerate(days, 1):
        try:
            rows = fetch(d)
        except Exception as e:                                    # noqa: BLE001
            print(f"  [{i}/{len(days)}] {d}  ❌ {type(e).__name__}: {e}")
            continue
        if not rows:
            tot_empty += 1
            print(f"  [{i}/{len(days)}] {d}  ⚠️ 上游無資料")
            time.sleep(args.sleep)
            continue
        if args.apply:
            new = upd = 0
            for doc in rows:
                r = col.update_one({"code": doc["code"], "date": doc["date"]},
                                   {"$set": doc}, upsert=True)
                if r.upserted_id:
                    new += 1
                elif r.modified_count:
                    upd += 1
            tot_new += new
            tot_upd += upd
            print(f"  [{i}/{len(days)}] {d}  {len(rows)} 筆 → 新增 {new} 更新 {upd}")
        else:
            print(f"  [{i}/{len(days)}] {d}  {len(rows)} 筆（DRY-RUN，未寫入）")
        time.sleep(args.sleep)

    print(f"\n完成：新增 {tot_new}　更新 {tot_upd}　上游無資料 {tot_empty} 天")
    if not args.apply:
        print("→ 加 --apply 才會實際寫入")


if __name__ == "__main__":
    main()
