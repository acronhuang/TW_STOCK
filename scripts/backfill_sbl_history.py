#!/usr/bin/env python3
"""回填 TWSE 上市借券成交明細歷史 → securities_lending_detail。

來源:TWSE `rwd/zh/lending/t13sa710`(歷史借券成交明細),用 startDate/endDate
(YYYYMMDD 無斜線!)按月查詢。補 2013 起的借券成交明細(原本只 2020-2026 稀疏)。
每月:delete 該月既有 TWSE_t13sa710 記錄 → insert(冪等)。

用法: backfill_sbl_history.py [--start 201301] [--end 202607]
"""
import argparse
import time
from datetime import datetime

import requests
from pymongo import MongoClient

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
URL = "https://www.twse.com.tw/rwd/zh/lending/t13sa710"


def roc_date(s):
    """114年06月02日 → datetime(2025,6,2)。"""
    s = str(s).strip()
    try:
        y = int(s.split("年")[0]) + 1911
        m = int(s.split("年")[1].split("月")[0])
        d = int(s.split("月")[1].split("日")[0])
        return datetime(y, m, d)
    except (ValueError, IndexError):
        return None


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_month(session, ym):
    y, m = ym // 100, ym % 100
    start = f"{y}{m:02d}01"
    end = f"{y}{m:02d}31"
    r = session.get(URL, params={"startDate": start, "endDate": end, "response": "json"},
                    headers={"User-Agent": UA}, timeout=40)
    j = r.json()
    if j.get("stat") != "OK":
        return None
    docs = []
    for row in j.get("data", []):
        if len(row) < 8:
            continue
        dt = roc_date(row[0])
        cn = str(row[1]).strip().split(" ", 1)   # "00648R 元大S&P500反1"
        code = cn[0]
        name = cn[1] if len(cn) > 1 else ""
        if not (dt and code):
            continue
        docs.append({
            "stock_id": code, "symbol": name, "date": dt,
            "transaction_type": str(row[2]).strip(),          # 競價/議借
            "volume": _num(row[3]),                           # 成交數量(張)
            "fee_rate": _num(row[4]),                         # 成交費率%
            "close": _num(row[5]),                            # 成交日收盤價
            "original_return_date": str(row[6]).strip(),      # 約定還券日期
            "original_lending_period": _num(row[7]),          # 約定借券天數
            "source": "TWSE_t13sa710", "updated_at": datetime.now(),
        })
    return docs


def month_iter(start, end):
    y, m = start // 100, start % 100
    while y * 100 + m <= end:
        yield y * 100 + m
        m += 1
        if m > 12:
            m = 1; y += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=201301)
    ap.add_argument("--end", type=int, default=int(datetime.now().strftime("%Y%m")))
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    col = db.securities_lending_detail
    session = requests.Session()

    months = list(month_iter(args.start, args.end))
    print(f"回填 {len(months)} 個月 ({args.start}~{args.end})")
    tot = 0
    for i, ym in enumerate(months, 1):
        try:
            docs = fetch_month(session, ym)
        except Exception as e:
            print(f"  {ym}: 失敗 {e}")
            time.sleep(args.delay)
            continue
        if docs is None:
            print(f"  {ym}: stat 非 OK")
        elif docs:
            y, m = ym // 100, ym % 100
            lo = datetime(y, m, 1)
            hi = datetime(y + (m // 12), (m % 12) + 1, 1)
            col.delete_many({"source": "TWSE_t13sa710", "date": {"$gte": lo, "$lt": hi}})
            col.insert_many(docs)
            tot += len(docs)
        if i % 12 == 0:
            print(f"  … {i}/{len(months)}  累計 {tot:,} 筆")
        time.sleep(args.delay)
    col.create_index([("stock_id", 1), ("date", 1)])
    col.create_index([("date", 1)])
    print(f"\n完成:securities_lending_detail 寫入 {tot:,} 筆 TWSE 借券明細")


if __name__ == "__main__":
    main()
