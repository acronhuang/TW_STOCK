#!/usr/bin/env python3
"""上櫃(TPEX)融資融券餘額每日同步 → margin_purchase_short_sale。

根因:每日 margin pipeline(twse_openapi MI_MARGN / backfill_margin_by_date)只收上市。
上櫃 margin(~913檔)過去只靠一次性 FinMind 回填才有;回填停後每天缺上櫃 → 完整度告警。
本 script 補上上櫃每日來源,寫入同一表同一 schema(code/margin_*/short_*)。

來源: tpex.org.tw/www/zh-tw/margin/balance?date=YYYY/MM/DD(西元斜線)
  tables[0] 20欄:0代號 1名 |融資 2前餘 3資買 4資賣 5現償 6資餘額 7證金 8使用率 9限額
                    |融券 10前餘 11券賣 12券買 13券償 14券餘額 15證金 16使用率 17限額 |18相抵 19備註
單位=張,與 TWSE MI_MARGN/FinMind 一致。date=午夜 naive datetime。upsert by (code,date)。

用法: tpex_margin_sync.py [--date 20260727] [--from 20260727 --to 20260728] [--daily]
"""
import argparse
import time
from datetime import datetime, timedelta

import requests
from pymongo import MongoClient, UpdateOne

URL = "https://www.tpex.org.tw/www/zh-tw/margin/balance"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"


def _int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch(session, d, retries=4):
    for i in range(retries):
        try:
            r = session.get(URL, params={"date": d.strftime("%Y/%m/%d"), "response": "json"},
                            headers={"User-Agent": UA}, timeout=30)
        except requests.RequestException:
            time.sleep(6 * (i + 1)); continue
        if r.status_code != 200:
            time.sleep(6 * (i + 1)); continue
        try:
            j = r.json()
        except ValueError:
            return "BLOCK"
        for t in j.get("tables", []):
            if t.get("data") and any("代號" in str(f) for f in t.get("fields", [])):
                return t
        return None
    return "ERR"


def to_docs(tbl, d):
    docs = []
    for row in tbl["data"]:
        if len(row) < 19:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        docs.append({
            "code": code, "name": str(row[1]).strip(), "date": d,
            "margin_prev_balance": _int(row[2]), "margin_buy": _int(row[3]),
            "margin_sell": _int(row[4]), "margin_cash_repay": _int(row[5]),
            "margin_balance": _int(row[6]), "margin_limit": _int(row[9]),
            "short_prev_balance": _int(row[10]), "short_sell": _int(row[11]),
            "short_buy": _int(row[12]), "short_cash_repay": _int(row[13]),
            "short_balance": _int(row[14]), "short_limit": _int(row[17]),
            "offset": _int(row[18]),
            "source": "TPEX:margin_balance", "market": "tpex",
            "updated_at": datetime.now(),
        })
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to", dest="to")
    ap.add_argument("--daily", action="store_true", help="抓最近交易日(cron 用)")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.margin_purchase_short_sale

    if args.date:
        days = [datetime.strptime(args.date, "%Y%m%d")]
    elif args.frm:
        lo = datetime.strptime(args.frm, "%Y%m%d")
        hi = datetime.strptime(args.to, "%Y%m%d") if args.to else lo
        days = sorted(datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
                      for r in db.trading_dates.find({}, {"date": 1, "_id": 0})
                      if len(str(r["date"])) >= 10
                      and lo <= datetime.strptime(str(r["date"])[:10], "%Y-%m-%d") <= hi)
    else:  # --daily:抓近5交易日補漏
        lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
        days = sorted(datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
                      for r in db.trading_dates.find({}, {"date": 1, "_id": 0})
                      if len(str(r["date"])) >= 10
                      and lat - timedelta(days=7) <= datetime.strptime(str(r["date"])[:10], "%Y-%m-%d") <= lat)
    session = requests.Session()
    tot = 0
    for d in days:
        tbl = fetch(session, d)
        if tbl in ("BLOCK", "ERR", None):
            print(f"  {d:%Y-%m-%d}: {tbl}(略過)", flush=True)
            time.sleep(args.delay); continue
        docs = to_docs(tbl, d)
        if docs:
            col.bulk_write([UpdateOne({"code": x["code"], "date": x["date"]},
                                      {"$set": x}, upsert=True) for x in docs], ordered=False)
            tot += len(docs)
            print(f"  {d:%Y-%m-%d}: 上櫃 margin {len(docs)} 檔", flush=True)
        time.sleep(args.delay)
    print(f"\n完成:TPEX margin 寫入 {tot:,} 筆", flush=True)


if __name__ == "__main__":
    main()
