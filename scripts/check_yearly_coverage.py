#!/usr/bin/env python3
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== 各年份 PE 覆蓋率分析 ===\n')

years = [2020, 2021, 2022, 2023, 2024]

for year in years:
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31)
    
    total = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end}
    })
    
    pe_count = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end},
        'pe_ratio': {'$exists': True, '$ne': None}
    })
    
    coverage = (pe_count/total*100) if total > 0 else 0
    print(f'{year}: {pe_count:,} / {total:,} = {coverage:.2f}%')

print(f'\n2025 (至今): ')
total_2025 = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2025, 1, 1)}
})
pe_2025 = db.stock_factors.count_documents({
    'date': {'$gte': datetime(2025, 1, 1)},
    'pe_ratio': {'$exists': True, '$ne': None}
})
coverage_2025 = (pe_2025/total_2025*100) if total_2025 > 0 else 0
print(f'       {pe_2025:,} / {total_2025:,} = {coverage_2025:.2f}%')

print(f'\n整體覆蓋率:')
total_all = db.stock_factors.count_documents({})
pe_all = db.stock_factors.count_documents({'pe_ratio': {'$exists': True, '$ne': None}})
coverage_all = (pe_all/total_all*100) if total_all > 0 else 0
print(f'  {pe_all:,} / {total_all:,} = {coverage_all:.2f}%')

client.close()
