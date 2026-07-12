#!/usr/bin/env python3
"""
診斷價值/質量因子覆蓋率低的問題
"""
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=' * 80)
print('財報數據診斷')
print('=' * 80)

# 檢查 financial_reports
fr_total = db.financial_reports.count_documents({})
fr_symbols = len(db.financial_reports.distinct('symbol'))
fr_valid = db.financial_reports.count_documents({'incomeStatement.netIncome': {'$gt': 0}})
fr_valid_symbols = len(db.financial_reports.distinct('symbol', {'incomeStatement.netIncome': {'$gt': 0}}))

print(f'\nfinancial_reports 集合:')
print(f'  總記錄數: {fr_total:,}')
print(f'  股票數量: {fr_symbols}')
print(f'  有效記錄 (netIncome > 0): {fr_valid:,}')
print(f'  有效股票數: {fr_valid_symbols}')

# 檢查 2330
doc_2330 = db.financial_reports.find_one({'symbol': '2330'})
if doc_2330:
    print(f'\n2330 財報數據:')
    print(f'  fiscalYear: {doc_2330.get("fiscalYear")}')
    print(f'  fiscalPeriod: {doc_2330.get("fiscalPeriod")}')
    print(f'  有 incomeStatement: {bool(doc_2330.get("incomeStatement"))}')
    print(f'  有 balanceSheet: {bool(doc_2330.get("balanceSheet"))}')
    if doc_2330.get('incomeStatement'):
        print(f'  netIncome: {doc_2330["incomeStatement"].get("netIncome")}')
    if doc_2330.get('balanceSheet'):
        print(f'  equity: {doc_2330["balanceSheet"].get("equity")}')
else:
    print('\n2330 無財報數據！')

# 檢查所有股票數量
all_symbols = len(db.stock_price.distinct('symbol'))
print(f'\n系統總股票數: {all_symbols}')
print(f'有財報的股票數: {fr_symbols} ({fr_symbols/all_symbols*100:.1f}%)')

# 檢查因子計算結果
print(f'\n因子數據統計:')
factor_total = db.stock_factors.count_documents({})
factor_with_pe = db.stock_factors.count_documents({'pe_ratio': {'$ne': None}})
factor_with_roe = db.stock_factors.count_documents({'roe': {'$ne': None}})

print(f'  因子總記錄數: {factor_total:,}')
print(f'  有 PE ratio: {factor_with_pe:,} ({factor_with_pe/factor_total*100:.2f}%)')
print(f'  有 ROE: {factor_with_roe:,} ({factor_with_roe/factor_total*100:.2f}%)')

# 隨機抽樣檢查
print(f'\n隨機抽樣 5 支股票的因子計算結果:')
sample_symbols = db.financial_reports.distinct('symbol')[:5]
for symbol in sample_symbols:
    # 檢查這支股票的因子記錄數
    factor_count = db.stock_factors.count_documents({
        'symbol': symbol,
        'pe_ratio': {'$ne': None}
    })
    print(f'  {symbol}: {factor_count:,} 筆有 PE ratio 的記錄')

print('=' * 80)

client.close()
