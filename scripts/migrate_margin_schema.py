#!/usr/bin/env python3
"""統一 margin_purchase_short_sale 的新舊 schema。

問題:舊 FinMind schema(string date + PascalCase 欄名)與新 TWSE OpenAPI schema
(datetime date + snake_case)混存。舊記錄 string date → 對 datetime 日期查詢隱形
(63280 筆,籌碼分析拿不到 2020~2025/08 歷史)。

修法(冪等):對每筆舊(string-date)記錄:
  1. 日期字串 → datetime(可查)
  2. 欄名正規化成新 schema(FinMind→OpenAPI)
  3. 若同 (code,date) 已有新 schema 記錄(重疊期重複)→ 刪舊(新勝)
     否則就地 replace 成正規化文件(保留 _id)

用法: migrate_margin_schema.py [--apply]
"""
import argparse
from datetime import datetime

from pymongo import MongoClient

OLD2NEW = {
    "stock_id": "code", "symbol": "name",
    "MarginPurchaseBuy": "margin_buy", "MarginPurchaseSell": "margin_sell",
    "MarginPurchaseCashRepayment": "margin_cash_repay",
    "MarginPurchaseTodayBalance": "margin_balance",
    "MarginPurchaseYesterdayBalance": "margin_prev_balance",
    "MarginPurchaseLimit": "margin_limit",
    "ShortSaleBuy": "short_buy", "ShortSaleSell": "short_sell",
    "ShortSaleCashRepayment": "short_cash_repay",
    "ShortSaleTodayBalance": "short_balance",
    "ShortSaleYesterdayBalance": "short_prev_balance",
    "ShortSaleLimit": "short_limit",
    "OffsetLoanAndShort": "offset", "Note": "note",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    c = db.margin_purchase_short_sale

    cur = c.find({"date": {"$type": "string"}})
    n_conv = n_dup = n_err = 0
    for old in cur:
        ds = old.get("date")
        code = old.get("stock_id")
        try:
            dt = datetime.strptime(str(ds)[:10], "%Y-%m-%d")
        except ValueError:
            n_err += 1
            continue
        if not code:
            n_err += 1
            continue
        # 重疊去重:同 code+date 已有新 schema 記錄?
        dup = c.find_one({"code": code, "date": dt, "_id": {"$ne": old["_id"]}})
        if dup:
            n_dup += 1
            if args.apply:
                c.delete_one({"_id": old["_id"]})
            continue
        # 正規化 replace
        newdoc = {"date": dt, "updated_at": old.get("updated_at") or datetime.now()}
        for ok, nk in OLD2NEW.items():
            if ok in old and old[ok] is not None:
                newdoc[nk] = old[ok]
        n_conv += 1
        if args.apply:
            c.replace_one({"_id": old["_id"]}, newdoc)

    print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} 正規化保留 {n_conv} 筆 / 重疊刪除 {n_dup} 筆 / 錯誤跳過 {n_err} 筆")
    if args.apply:
        left = c.count_documents({"date": {"$type": "string"}})
        tot_date = c.count_documents({"date": {"$type": "date"}})
        print(f"完成後: string-date 殘留 {left} 筆, date型 {tot_date} 筆")


if __name__ == "__main__":
    main()
