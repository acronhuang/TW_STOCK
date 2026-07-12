#!/usr/bin/env python3
"""
檢查因子數據質量（實際有值的比例）
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

total = db.stock_factors.count_documents({})
momentum_exists = db.stock_factors.count_documents({'return_1m': {'$exists': True, '$ne': None}})
value_exists = db.stock_factors.count_documents({'pe_ratio': {'$exists': True, '$ne': None}})
quality_exists = db.stock_factors.count_documents({'roe': {'$exists': True, '$ne': None}})

print('=' * 80)
print('各因子實際有值的記錄數統計（2020-2025）')
print('=' * 80)
print(f'總記錄數:       {total:,}')
print()
print(f'動能因子 (有 return_1m 值): {momentum_exists:,} ({momentum_exists/total*100:.2f}%)')
print(f'價值因子 (有 pe_ratio 值):  {value_exists:,} ({value_exists/total*100:.2f}%)')
print(f'質量因子 (有 roe 值):       {quality_exists:,} ({quality_exists/total*100:.2f}%)')
print('=' * 80)
print()

# 按年份統計
import pandas as pd
from datetime import datetime

years = [2020, 2021, 2022, 2023, 2024, 2025]
stats = []

for year in years:
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31)
    
    year_total = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end}
    })
    
    year_momentum = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end},
        'return_1m': {'$ne': None}
    })
    
    year_value = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end},
        'pe_ratio': {'$ne': None}
    })
    
    year_quality = db.stock_factors.count_documents({
        'date': {'$gte': start, '$lte': end},
        'roe': {'$ne': None}
    })
    
    stats.append({
        'Year': year,
        'Total': f'{year_total:,}',
        'Momentum%': f'{year_momentum/year_total*100:.1f}%' if year_total > 0 else 'N/A',
        'Value%': f'{year_value/year_total*100:.1f}%' if year_total > 0 else 'N/A',
        'Quality%': f'{year_quality/year_total*100:.1f}%' if year_total > 0 else 'N/A'
    })

df = pd.DataFrame(stats)
print('年度因子覆蓋率統計:')
print('-' * 80)
print(df.to_string(index=False))
print('=' * 80)

client.close()
