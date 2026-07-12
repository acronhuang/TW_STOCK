#!/usr/bin/env python3
"""
月營收同步（免費官方 OpenAPI，取代 FinMind 配額限制）
=====================================================
來源（整批抓全市場，不耗 FinMind 配額）：
  上市 TWSE : https://openapi.twse.com.tw/v1/opendata/t187ap05_L
  上櫃 TPEX : https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O
寫入 monthly_revenue（schema: symbol/year_month/revenue/last_month_revenue/mom_growth/name/industry/data_source）。
驗證：值與 FinMind 一致(千元)、且更新較快。涵蓋 上市1082+上櫃890 ≈ 99%。

用法： python scripts/sync_revenue_openapi.py [--dry-run]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from src.utils.twstock_openapi import fetch_openapi, to_float, roc_year_month

TWSE = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TPEX = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O'


def fetch(url, src):
    rows = []
    for x in fetch_openapi(url):
        ym = roc_year_month(x.get('資料年月', ''))
        sym = str(x.get('公司代號', '')).strip()
        rev = to_float(x.get('營業收入-當月營收'))
        if not (ym and sym and sym.isdigit() and rev is not None):
            continue
        rows.append({
            'symbol': sym, 'year_month': ym, 'revenue': rev,
            'last_month_revenue': to_float(x.get('營業收入-上月營收')),
            'mom_growth': to_float(x.get('營業收入-上月比較增減(%)')),
            'yoy_growth': to_float(x.get('營業收入-去年同月增減(%)')),   # 消費端(蔡森評分/因子排行)有讀
            'last_year_revenue': to_float(x.get('營業收入-去年當月營收')),
            'name': x.get('公司名稱', ''), 'industry': x.get('產業別', ''),
            'data_source': src, 'updated_at': datetime.now(),
        })
    return rows


def main():
    dry = '--dry-run' in sys.argv
    db = MongoClient('localhost', 27017)['tw_stock_analysis']
    rows = fetch(TWSE, 'TWSE_OpenAPI') + fetch(TPEX, 'TPEX_OpenAPI')
    if not rows:
        print("⚠️ 無資料"); return
    ym = sorted({r['year_month'] for r in rows})
    print(f"抓到 {len(rows)} 筆（年月 {ym}）；上市/上櫃合計")
    if dry:
        for r in rows[:3]:
            print("  ", r)
        return
    ops = [UpdateOne({'symbol': r['symbol'], 'year_month': r['year_month']},
                     {'$set': r}, upsert=True) for r in rows]
    res = db.monthly_revenue.bulk_write(ops, ordered=False)
    print(f"✅ upsert：新增 {res.upserted_count}  更新 {res.modified_count}")


if __name__ == '__main__':
    main()
