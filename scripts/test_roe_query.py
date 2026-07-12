#!/usr/bin/env python3
"""
檢查 ROE 查詢的問題
"""

from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== ROE 查詢測試 ===\n')

total = db.stock_factors.count_documents({})
print(f'stock_factors 總記錄數: {total:,}')

# 測試不同查詢
print('\n不同查詢結果:')

q1 = db.stock_factors.count_documents({
    'roe': {'$exists': True}
})
print(f'1. roe $exists True:                  {q1:,} ({q1/total*100:.1f}%)')

q2 = db.stock_factors.count_documents({
    'roe': {'$exists': True, '$ne': None}
})
print(f'2. roe $exists True, $ne None:        {q2:,} ({q2/total*100:.1f}%)')

q3 = db.stock_factors.count_documents({
    'roe': {'$exists': True, '$ne': None, '$ne': 0}
})
print(f'3. roe $exists True, $ne None, $ne 0: {q3:,} ({q3/total*100:.1f}%)')

# 抽樣檢查 roe 欄位的值
print('\n抽樣 10 筆記錄的 roe 值:')
samples = list(db.stock_factors.find({}).limit(10))
for i, doc in enumerate(samples, 1):
    symbol = doc.get('symbol')
    roe = doc.get('roe')
    print(f'  {i}. {symbol}: roe={roe} (type: {type(roe).__name__})')

client.close()
