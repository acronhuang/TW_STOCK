#!/usr/bin/env python3
"""回填融資融券餘額歷史 → margin_purchase_short_sale(新snake schema)。

來源:TWSE `rwd/zh/marginTrading/TWT93U`(信用額度總量管制餘額表,逐股融資融券餘額),
單日查詢。補 2013-2024(原 FinMind 只 ~40檔/日稀疏;TWT93U ~1000檔/日全)。
只查 trading_dates 交易日。upsert by (code,date) → 覆蓋稀疏舊資料。

TWT93U 15欄: 0代號 1名稱 | 融資:2前日餘額 3賣出 4買進 5現券 6今日餘額 7限額
                        | 融券:8前日餘額 9當日賣出 10當日還券 11當日調整 12當日餘額 13限額 | 14備註

用法: backfill_margin_twt93u.py [--start 20130101] [--end 20241231]
"""
import argparse
import time
from datetime import datetime

import requests
from pymongo import MongoClient, UpdateOne

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
URL = "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U"
NO_STOP = {"債券ETF", "長期存股", "零成本", "零股"}


def _i(x):
    try:
        return int(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_day(session, d):
    r = session.get(URL, params={"date": d.strftime("%Y%m%d"), "response": "json"},
                    headers={"User-Agent": UA}, timeout=40)
    j = r.json()
    if j.get("stat") != "OK":
        return None
    docs = []
    for row in j.get("data", []):
        if len(row) < 14:
            continue
        code = str(row[0]).strip()
        if not code:
            continue
        docs.append({
            "code": code, "name": str(row[1]).strip(), "date": d,
            "margin_prev_balance": _i(row[2]), "margin_sell": _i(row[3]),
            "margin_buy": _i(row[4]), "margin_cash_repay": _i(row[5]),
            "margin_balance": _i(row[6]), "margin_limit": _i(row[7]),
            "short_prev_balance": _i(row[8]), "short_sell": _i(row[9]),
            "short_cash_repay": _i(row[10]), "offset": _i(row[11]),
            "short_balance": _i(row[12]), "short_limit": _i(row[13]),
            "note": str(row[14]).strip() if len(row) > 14 else "",
            "source": "TWSE_TWT93U", "updated_at": datetime.now(),
        })
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20130101")
    ap.add_argument("--end", default="20241231")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.margin_purchase_short_sale
    lo = datetime.strptime(args.start, "%Y%m%d")
    hi = datetime.strptime(args.end, "%Y%m%d")

    # 只查交易日(trading_dates,字串date)
    days = sorted(datetime.strptime(str(r["date"])[:10], "%Y-%m-%d")
                  for r in db.trading_dates.find({}, {"date": 1, "_id": 0})
                  if len(str(r["date"])) >= 10 and lo <= datetime.strptime(str(r["date"])[:10], "%Y-%m-%d") <= hi)
    # 續跑:跳過已有 TWT93U 資料的日期(TWSE rwd 會反爬封鎖,需分批慢跑)
    done = set(db.margin_purchase_short_sale.distinct(
        "date", {"source": "TWSE_TWT93U", "date": {"$gte": lo, "$lte": hi}}))
    days = [d for d in days if d not in done]
    session = requests.Session()
    print(f"回填 {len(days)} 交易日 (跳過已補 {len(done)};TWSE反爬,建議 --delay 3+ 分批)")
    consec_fail = 0
    tot = 0
    for i, d in enumerate(days, 1):
        try:
            docs = fetch_day(session, d)
            consec_fail = 0
        except Exception as e:
            consec_fail += 1
            print(f"  {d:%Y-%m-%d}: 失敗 {e}")
            if consec_fail >= 5:
                print(f"⛔ 連續 {consec_fail} 次失敗(TWSE 反爬封鎖)→ 中止;冷卻後 --resume 續跑")
                break
            time.sleep(args.delay * 3)
            continue
        if docs:
            col.bulk_write([UpdateOne({"code": x["code"], "date": x["date"]},
                                      {"$set": x}, upsert=True) for x in docs], ordered=False)
            tot += len(docs)
        if i % 60 == 0:
            print(f"  … {i}/{len(days)} ({d:%Y-%m})  累計 {tot:,} 筆")
        time.sleep(args.delay)
    print(f"\n完成:融資融券餘額回填 {tot:,} 筆(TWSE_TWT93U)")


if __name__ == "__main__":
    main()
