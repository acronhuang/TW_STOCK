#!/usr/bin/env python3
"""
檢查 taiwan_stock_info 中 outstanding_shares 的實際數據狀況
"""
from pymongo import MongoClient
import json

db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']

print('=' * 80)
print('taiwan_stock_info.outstanding_shares 數據檢查')
print('=' * 80)

# 統計
total = db.taiwan_stock_info.count_documents({})
with_field = db.taiwan_stock_info.count_documents({'outstanding_shares': {'$exists': True}})
with_value = db.taiwan_stock_info.count_documents({'outstanding_shares': {'$gt': 0}})

print(f'\ntaiwan_stock_info 總記錄數: {total:,}')
print(f'有 outstanding_shares 欄位: {with_field:,} ({with_field/total*100:.1f}%)')
print(f'outstanding_shares > 0: {with_value:,} ({with_value/total*100:.1f}%)')

# 看一筆有 outstanding_shares 的記錄
print('\n' + '=' * 80)
print('有 outstanding_shares 的樣本記錄:')
print('=' * 80)
doc = db.taiwan_stock_info.find_one({'outstanding_shares': {'$exists': True}})
if doc:
    print(f'\nstock_id: {doc.get("stock_id")}')
    print(f'outstanding_shares: {doc.get("outstanding_shares"):,}')
    print(f'\n所有欄位: {list(doc.keys())}')
    print(f'\n完整記錄:')
    print(json.dumps({k: v for k, v in doc.items() if k != '_id'}, indent=2, default=str))
else:
    print('\n❌ 沒有找到有 outstanding_shares 的記錄')

# 看一筆沒有 outstanding_shares 的記錄  
print('\n' + '=' * 80)
print('沒有 outstanding_shares 的樣本記錄:')
print('=' * 80)
doc2 = db.taiwan_stock_info.find_one({'outstanding_shares': {'$exists': False}})
if doc2:
    print(f'\nstock_id: {doc2.get("stock_id")}')
    print(f'所有欄位: {list(doc2.keys())}')
    print(f'\n完整記錄:')
    print(json.dumps({k: v for k, v in doc2.items() if k != '_id'}, indent=2, default=str))
else:
    print('\n✅ 所有記錄都有 outstanding_shares 欄位')

# 列出前 10 筆有 outstanding_shares 的股票
print('\n' + '=' * 80)
print('前 10 筆有 outstanding_shares 的股票:')
print('=' * 80)
docs = list(db.taiwan_stock_info.find({'outstanding_shares': {'$exists': True}}).limit(10))
for doc in docs:
    print(f"{doc.get('stock_id'):8s}  {doc.get('outstanding_shares', 0):>15,.0f} 千股")

print('\n' + '=' * 80)
