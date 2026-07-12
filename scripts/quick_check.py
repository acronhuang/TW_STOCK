#!/usr/bin/env python3
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== 2024-2025 期間數據分析 ===\n')

# 1. stock_factors 覆蓋率
total = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)}
})
pe = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)},
    'pe_ratio': {'$exists': True, '$ne': None}
})

print(f'stock_factors (2024-2025):')
print(f'  總記錄: {total:,}')
print(f'  有 PE:  {pe:,} ({pe/total*100:.1f}%)\n')

# 2. taiwan_stock_per
per_total = db.taiwan_stock_per.count_documents({})
per_2024 = db.taiwan_stock_per.count_documents({
    'date': {'$gte': datetime(2024,1,1), '$lte': datetime(2025,2,23)}
})

print(f'taiwan_stock_per:')
print(f'  總記錄: {per_total:,}')
print(f'  2024-2025: {per_2024:,} ({per_2024/per_total*100:.1f}%)\n')

# 3. 測試具體數據
print('測試 2330 @ 2024-02-20:')
factor = db.stock_factors.find_one({'symbol': '2330', 'date': datetime(2024,2,20)})
per_doc = db.taiwan_stock_per.find_one({'stock_id': '2330', 'date': datetime(2024,2,20)})

if factor:
    print(f'  stock_factors.pe_ratio: {factor.get("pe_ratio")}')
else:
    print(f'  stock_factors: 無記錄')

if per_doc:
    print(f'  taiwan_stock_per.PER: {per_doc.get("PER")}')
else:
    print(f'  taiwan_stock_per: 無記錄')

client.close()
