#!/usr/bin/env python3
"""
發行股數同步（免費官方 OpenAPI，取代 FinMind TaiwanStockBalanceSheet）
=====================================================================
來源（整批抓全市場，不耗 FinMind 配額）：
  上市 TWSE : t187ap03_L「已發行普通股數或TDR原股發行股數」(實際股數)
  上櫃 TPEX : mopsfin_t187ap03_O「IssueShares」(實際股數)
寫入 taiwan_stock_info.outstanding_shares。**單位：千股**（= 實際股數 / 1000，
與既有 DB 慣例一致；驗證 2330/1240/5274 API/DB 比值=1000）。涵蓋 上市1090+上櫃890 ≈ 99%。

用法： python scripts/sync_shares_openapi.py [--dry-run]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from src.utils.twstock_openapi import fetch_openapi, to_float

# (url, 代號欄, 發行股數欄)：上市 TWSE / 上櫃 TPEX
SOURCES = [
    ('https://openapi.twse.com.tw/v1/opendata/t187ap03_L', '公司代號', '已發行普通股數或TDR原股發行股數'),
    ('https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O', 'SecuritiesCompanyCode', 'IssueShares'),
]


def fetch_shares(url, code_key, shares_key):
    """回 {股號: 千股}。實際股數 ÷1000 = DB 慣例(千股)。"""
    out = {}
    for x in fetch_openapi(url):
        sid = str(x.get(code_key, '')).strip()
        sh = to_float(x.get(shares_key))
        if sid.isdigit() and sh:
            out[sid] = sh / 1000.0
    return out


def main():
    dry = '--dry-run' in sys.argv
    db = MongoClient('localhost', 27017)['tw_stock_analysis']
    shares = {}
    for url, code_key, shares_key in SOURCES:
        shares.update(fetch_shares(url, code_key, shares_key))
    if not shares:
        print("⚠️ 無資料"); return
    print(f"抓到 {len(shares)} 檔發行股數(千股)")
    if dry:
        for s in ['2330', '1240', '6488', '8069']:
            print(f"  {s}: {shares.get(s)}")
        return
    now = datetime.now()
    ops = [UpdateOne({'stock_id': sid},
                     {'$set': {'outstanding_shares': sh, 'shares_source': 'OpenAPI',
                               'shares_updated_at': now}},
                     upsert=True) for sid, sh in shares.items()]
    res = db.taiwan_stock_info.bulk_write(ops, ordered=False)
    print(f"✅ upsert：新增 {res.upserted_count}  更新 {res.modified_count}")


if __name__ == '__main__':
    main()
