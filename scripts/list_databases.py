#!/usr/bin/env python3
"""
檢查所有資料庫中的相關集合
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')

print('=' * 80)
print('檢查所有相關資料庫')
print('=' * 80)

for db_name in client.list_database_names():
    if 'stock' in db_name.lower() or 'tw' in db_name.lower():
        db = client[db_name]
        collections = db.list_collection_names()
        
        print(f'\n📦 {db_name}:')
        print(f'   集合數: {len(collections)}')
        
        # 檢查關鍵集合
        if 'taiwan_stock_info' in collections:
            count = db.taiwan_stock_info.count_documents({})
            with_shares = db.taiwan_stock_info.count_documents({'outstanding_shares': {'$exists': True, '$ne': None, '$ne': 0}})
            print(f'   ✓ taiwan_stock_info: {count:,} 筆記錄 ({with_shares:,} 有 outstanding_shares)')
        
        if 'stock_factors' in collections:
            count = db.stock_factors.count_documents({})
            print(f'   ✓ stock_factors: {count:,} 筆記錄')
            
        if 'financial_reports' in collections:
            count = db.financial_reports.count_documents({})
            print(f'   ✓ financial_reports: {count:,} 筆記錄')
            
        if 'stock_price' in collections:
            count = db.stock_price.count_documents({})
            print(f'   ✓ stock_price: {count:,} 筆記錄')

client.close()
