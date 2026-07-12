#!/usr/bin/env python3
"""
檢查 financial_reports 數據質量
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*80)
print('financial_reports 數據質量檢查')
print('='*80)

# 總記錄數
total = db.financial_reports.count_documents({})
print(f'\n總記錄數: {total:,}')

# 有 incomeStatement 的記錄
有income = db.financial_reports.count_documents({'incomeStatement': {'$exists': True}})
print(f'有 incomeStatement: {有income:,} ({有income/total*100:.1f}%)')

# netIncome > 0 的記錄
netIncome有效 = db.financial_reports.count_documents({'incomeStatement.netIncome': {'$gt': 0}})
print(f'netIncome > 0: {netIncome有效:,} ({netIncome有效/total*100:.1f}%)')

# netIncome = 0 的記錄
netIncome為0 = db.financial_reports.count_documents({'incomeStatement.netIncome': 0})
print(f'netIncome = 0: {netIncome為0:,} ({netIncome為0/total*100:.1f}%)')

# netIncome < 0 的記錄（虧損）
netIncome負 = db.financial_reports.count_documents({'incomeStatement.netIncome': {'$lt': 0}})
print(f'netIncome < 0 (虧損): {netIncome負:,} ({netIncome負/total*100:.1f}%)')

print()

# 有 balanceSheet 的記錄
有balance = db.financial_reports.count_documents({'balanceSheet': {'$exists': True}})
print(f'有 balanceSheet: {有balance:,} ({有balance/total*100:.1f}%)')

# equity > 0 的記錄
equity有效 = db.financial_reports.count_documents({'balanceSheet.equity': {'$gt': 0}})
print(f'equity > 0: {equity有效:,} ({equity有效/total*100:.1f}%)')

# equity = 0 的記錄
equity為0 = db.financial_reports.count_documents({'balanceSheet.equity': 0})
print(f'equity = 0: {equity為0:,} ({equity為0/total*100:.1f}%)')

print()
print('='*80)
print('結論')
print('='*80)

# 可用於計算 PE 的記錄（netIncome > 0）
可算PE = netIncome有效
print(f'✅ 可計算 PE ratio 的記錄: {可算PE:,} ({可算PE/total*100:.1f}%)')

# 可用於計算 PB 的記錄（equity > 0）
可算PB = equity有效
print(f'✅ 可計算 PB ratio 的記錄: {可算PB:,} ({可算PB/total*100:.1f}%)')

# 同時可計算 PE 和 PB 的記錄
同時可算 = db.financial_reports.count_documents({
    'incomeStatement.netIncome': {'$gt': 0},
    'balanceSheet.equity': {'$gt': 0}
})
print(f'✅ 同時可計算 PE+PB 的記錄: {同時可算:,} ({同時可算/total*100:.1f}%)')

print()
if 可算PE / total < 0.5:
    print('⚠️  警告: 超過 50% 的財報記錄 netIncome = 0')
    print('   這會導致大部分因子記錄無法計算 PE/ROE')
    print()
    print('可能原因:')
    print('1. 數據下載時沒有正確解析 netIncome 欄位')
    print('2. FinMind 返回的數據結構與預期不符')
    print('3. 數據類型轉換問題')
else:
    print('✅ 財報數據質量良好')

# 隨機抽樣檢查
print()
print('='*80)
print('隨機抽樣 5 筆財報記錄')
print('='*80)

samples = db.financial_reports.find().limit(5)
for i, doc in enumerate(samples, 1):
    print(f'\n樣本 {i}:')
    print(f'  symbol: {doc.get("symbol")}')
    print(f'  fiscalYear: {doc.get("fiscalYear")}')
    print(f'  fiscalPeriod: {doc.get("fiscalPeriod")}')
    if doc.get('incomeStatement'):
        print(f'  netIncome: {doc["incomeStatement"].get("netIncome")}')
    if doc.get('balanceSheet'):
        print(f'  equity: {doc["balanceSheet"].get("equity")}')

client.close()
