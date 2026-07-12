#!/usr/bin/env python3
"""一次性腳本：補回 2026-03-31 缺失的股價資料（透過 FinMind API）"""

import os
import sys
import time
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from pymongo import MongoClient
from bson.decimal128 import Decimal128

TOKEN = os.environ.get('FINMIND_API_TOKEN', '')
client = MongoClient('localhost', 27017)
col = client['tw_stock_analysis']['stock_price']
DT = datetime(2026, 3, 31)

# 找出缺失的股票
existing_331 = set(doc['stock_id'] for doc in col.find({'date': DT}, {'stock_id': 1}))
all_ids = col.distinct('stock_id')
missing = [sid for sid in all_ids if sid not in existing_331]
print(f'缺失 3/31 資料: {len(missing)} 支股票')

if not missing:
    print('全部已補齊！')
    # 自行刪除此腳本的 launchd plist
    plist = os.path.expanduser('~/Library/LaunchAgents/com.twstock.backfill_331.plist')
    if os.path.exists(plist):
        os.system(f'launchctl bootout gui/501 {plist} 2>/dev/null')
        os.remove(plist)
        print('已移除排程')
    sys.exit(0)

inserted = 0
errors = 0
rate_limited = False

for i, sid in enumerate(missing):
    if rate_limited:
        break
    try:
        r = requests.get('https://api.finmindtrade.com/api/v4/data', params={
            'dataset': 'TaiwanStockPrice',
            'data_id': sid,
            'start_date': '2026-03-31',
            'end_date': '2026-03-31',
            'token': TOKEN,
        }, timeout=10)

        if r.status_code == 402 or r.status_code == 429:
            print(f'API 額度用完 (已處理 {i}/{len(missing)}, 新增 {inserted})')
            rate_limited = True
            break

        if r.status_code == 200:
            rows = r.json().get('data', [])
            for row in rows:
                doc = {
                    'stock_id': sid, 'symbol': sid,
                    'date': DT,
                    'open': Decimal128(str(row.get('open', 0))),
                    'high': Decimal128(str(row.get('max', 0))),
                    'low': Decimal128(str(row.get('min', 0))),
                    'close': Decimal128(str(row.get('close', 0))),
                    'adj_close': Decimal128(str(row.get('close', 0))),
                    'volume': Decimal128(str(row.get('Trading_Volume', 0))),
                    'amount': str(row.get('Trading_money', 0)),
                    'change': str(row.get('spread', 0)),
                    'data_source': 'FinMind_backfill',
                    'updated_at': datetime.utcnow(),
                }
                col.update_one({'stock_id': sid, 'date': DT}, {'$set': doc}, upsert=True)
                inserted += 1
    except Exception:
        errors += 1

    if i > 0 and i % 100 == 0:
        print(f'  進度: {i}/{len(missing)}, 新增={inserted}')

remaining = len(missing) - inserted
print(f'完成！新增: {inserted}, 錯誤: {errors}, 剩餘: {remaining}')
total = col.count_documents({'date': DT})
print(f'3/31 總記錄: {total}')

if remaining == 0:
    print('全部補齊！移除排程...')
    plist = os.path.expanduser('~/Library/LaunchAgents/com.twstock.backfill_331.plist')
    if os.path.exists(plist):
        os.system(f'launchctl bootout gui/501 {plist} 2>/dev/null')
        os.remove(plist)
