#!/usr/bin/env python3
from pymongo import MongoClient
import json

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== financial_reports 結構分析 ===\n')

# 1. 總記錄數和涵蓋股票
total = db.financial_reports.count_documents({})
pipeline = [
    {'$group': {'_id': '$symbol'}},
    {'$count': 'unique_stocks'}
]
result = list(db.financial_reports.aggregate(pipeline))
unique_stocks = result[0]['unique_stocks'] if result else 0

print(f'總記錄數: {total:,}')
print(f'涵蓋股票數: {unique_stocks}')

# 2. 檢查各欄位覆蓋率
print('\n【欄位覆蓋率】:')

has_income = db.financial_reports.count_documents({
    'incomeStatement': {'$exists': True, '$ne': None}
})
print(f'incomeStatement: {has_income:,} ({has_income/total*100:.1f}%)')

has_balance = db.financial_reports.count_documents({
    'balanceSheet': {'$exists': True, '$ne': None}
})
print(f'balanceSheet: {has_balance:,} ({has_balance/total*100:.1f}%)')

has_net_income = db.financial_reports.count_documents({
    'incomeStatement.netIncome': {'$exists': True, '$ne': None}
})
print(f'netIncome: {has_net_income:,} ({has_net_income/total*100:.1f}%)')

has_equity = db.financial_reports.count_documents({
    'balanceSheet.equity': {'$exists': True, '$ne': None}
})
print(f'equity: {has_equity:,} ({has_equity/total*100:.1f}%)')

has_assets = db.financial_reports.count_documents({
    'balanceSheet.totalAssets': {'$exists': True, '$ne': None}
})
print(f'totalAssets: {has_assets:,} ({has_assets/total*100:.1f}%)')

# 3. 抽樣一筆完整記錄
print('\n【抽樣一筆完整記錄】（2330）:')
sample = db.financial_reports.find_one({'symbol': '2330'})

if sample:
    print(f'\n股票: {sample.get("symbol")}')
    print(f'年份: {sample.get("fiscalYear")}')
    print(f'季度: Q{sample.get("fiscalPeriod")}')
    
    if 'incomeStatement' in sample:
        income = sample['incomeStatement']
        print(f'\nincomeStatement 欄位:')
        for key in list(income.keys())[:10]:
            print(f'  {key}: {income[key]}')
    
    if 'balanceSheet' in sample:
        balance = sample['balanceSheet']
        print(f'\nbalanceSheet 欄位:')
        for key in list(balance.keys())[:10]:
            print(f'  {key}: {balance[key]}')

client.close()
