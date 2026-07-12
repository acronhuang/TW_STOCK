#!/usr/bin/env python3
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== 檢查實際的 PE/PB 值 ===\n')

# 1. 檢查 2024-2025 有多少記錄的 PE 不是 None
total_2024 = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)}
})

pe_exists = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)},
    'pe_ratio': {'$exists': True}  # 欄位存在
})

pe_not_null = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)},
    'pe_ratio': {'$exists': True, '$ne': None}  # 欄位存在且不是 None
})

print(f'2024-2025 期間 stock_factors:')
print(f'  總記錄:          {total_2024:,}')
print(f'  pe_ratio 欄位存在: {pe_exists:,} ({pe_exists/total_2024*100:.1f}%)')
print(f'  pe_ratio 有值:   {pe_not_null:,} ({pe_not_null/total_2024*100:.1f}%)')
print()

# 2. 抽樣檢查幾筆 2024 記錄的 PE 值
print('抽樣檢查（2024 年前 10 筆）:')
samples = list(db.stock_factors.find({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2024,12,31)}
}).sort('date', 1).limit(10))

for i, doc in enumerate(samples, 1):
    symbol = doc.get('symbol')
    date = doc.get('date').strftime('%Y-%m-%d')
    pe = doc.get('pe_ratio')
    pb = doc.get('pb_ratio')
    print(f'  {i}. {symbol} @ {date}: PE={pe}, PB={pb}')

print()

# 3. 檢查 2330 在 2024 年的數據
print('檢查 2330 在 2024 年的數據:')
docs_2330 = list(db.stock_factors.find({
    'symbol': '2330',
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2024,12,31)}
}).sort('date', 1).limit(10))

if docs_2330:
    for doc in docs_2330:
        date = doc.get('date').strftime('%Y-%m-%d')
        pe = doc.get('pe_ratio')
        pb = doc.get('pb_ratio')
        print(f'  {date}: PE={pe}, PB={pb}')
else:
    print('  無記錄')

client.close()
