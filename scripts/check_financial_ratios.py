#!/usr/bin/env python3
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== financial_reports 中的 financialRatios 分析 ===\n')

# 1. 總記錄數
total = db.financial_reports.count_documents({})
print(f'financial_reports 總記錄數: {total:,}')

# 2. 有 financialRatios 的記錄數
has_ratios = db.financial_reports.count_documents({
    'financialRatios': {'$exists': True, '$ne': None}
})
print(f'有 financialRatios: {has_ratios:,} ({has_ratios/total*100:.1f}%)')

# 3. 有 ROE 的記錄數
has_roe = db.financial_reports.count_documents({
    'financialRatios.roe': {'$exists': True, '$ne': None}
})
print(f'有 ROE: {has_roe:,} ({has_roe/total*100:.1f}%)')

# 4. 有 ROA 的記錄數
has_roa = db.financial_reports.count_documents({
    'financialRatios.roa': {'$exists': True, '$ne': None}
})
print(f'有 ROA: {has_roa:,} ({has_roa/total*100:.1f}%)')

# 5. 涵蓋多少股票
pipeline = [
    {'$match': {'financialRatios.roe': {'$exists': True, '$ne': None}}},
    {'$group': {'_id': '$symbol'}},
    {'$count': 'unique_stocks'}
]
result = list(db.financial_reports.aggregate(pipeline))
unique_stocks = result[0]['unique_stocks'] if result else 0
print(f'\n有 ROE 的股票數: {unique_stocks}')

# 6. 抽樣
print('\n抽樣 5 筆（有 financialRatios）:')
samples = list(db.financial_reports.find({
    'financialRatios': {'$exists': True, '$ne': None}
}).limit(5))

for doc in samples:
    symbol = doc.get('symbol')
    year = doc.get('fiscalYear')
    period = doc.get('fiscalPeriod')
    ratios = doc.get('financialRatios', {})
    roe = ratios.get('roe')
    roa = ratios.get('roa')
    print(f'  {symbol} {year}Q{period}: ROE={roe}, ROA={roa}')

client.close()
