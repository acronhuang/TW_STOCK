#!/usr/bin/env python3
"""
測試單支股票（2330）的價值/質量因子計算
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pymongo import MongoClient
from datetime import datetime
from factors.value_factors import ValueFactors
from factors.quality_factors import QualityFactors

# 連接資料庫
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*80)
print('測試 2330 台積電的因子計算')
print('='*80)

# 1. 檢查財報數據
print('\n1. 檢查財報數據:')
print('-'*80)

fr = db.financial_reports.find_one({'symbol': '2330'}, sort=[('fiscalYear', -1), ('fiscalPeriod', -1)])
if fr:
    print(f'✅ financial_reports 有數據')
    print(f'   fiscalYear: {fr.get("fiscalYear")}')
    print(f'   fiscalPeriod: {fr.get("fiscalPeriod")}')
    print(f'   有 incomeStatement: {bool(fr.get("incomeStatement"))}')
    print(f'   有 balanceSheet: {bool(fr.get("balanceSheet"))}')
    if fr.get('incomeStatement'):
        print(f'   netIncome: {fr["incomeStatement"].get("netIncome")}')
    if fr.get('balanceSheet'):
        print(f'   equity: {fr["balanceSheet"].get("equity")}')
else:
    print('❌ financial_reports 無數據')

# 2. 檢查流通股數
print('\n2. 檢查流通股數:')
print('-'*80)

stock_info = db.taiwan_stock_info.find_one({'stock_id': '2330'}, sort=[('date', -1)])
if stock_info:
    print(f'✅ taiwan_stock_info 有數據')
    print(f'   stock_id: {stock_info.get("stock_id")}')
    print(f'   date: {stock_info.get("date")}')
    print(f'   outstanding_shares: {stock_info.get("outstanding_shares")} (千股)')
else:
    print('❌ taiwan_stock_info 無數據')

# 3. 檢查價格數據
print('\n3. 檢查價格數據:')
print('-'*80)

test_date = datetime(2024, 12, 31)
price_doc = db.stock_price.find_one({'symbol': '2330', 'date': test_date})
if price_doc:
    print(f'✅ 2024-12-31 有價格數據')
    print(f'   close: {price_doc.get("close")}')
else:
    print('❌ 2024-12-31 無價格數據')
    # 找最近的日期
    latest = db.stock_price.find_one({'symbol': '2330'}, sort=[('date', -1)])
    if latest:
        test_date = latest['date']
        price_doc = latest
        print(f'✅ 改用最新日期: {test_date}')
        print(f'   close: {price_doc.get("close")}')

# 4. 測試因子計算
print('\n4. 測試因子計算:')
print('-'*80)

value_factors = ValueFactors(db)
quality_factors = QualityFactors(db)

print(f'\n測試日期: {test_date}')

# 計算 PE
print('\n計算 PE Ratio...')
try:
    pe = value_factors.calculate_pe_ratio('2330', test_date)
    if pe:
        print(f'✅ PE Ratio = {pe:.2f}')
    else:
        print('❌ PE Ratio = None')
        print('   開始逐步診斷...')
        
        # 診斷步驟
        price_result = db.stock_price.find_one({'symbol': '2330', 'date': test_date})
        print(f'   - 價格查詢: {"✅" if price_result else "❌"}')
        
        financial_result = db.financial_reports.find_one(
            {'symbol': '2330', 'incomeStatement.netIncome': {'$gt': 0}},
            sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
        )
        print(f'   - 財報查詢 (netIncome > 0): {"✅" if financial_result else "❌"}')
        if financial_result:
            print(f'     netIncome: {financial_result.get("incomeStatement", {}).get("netIncome")}')
        
        stock_info_result = db.taiwan_stock_info.find_one(
            {'stock_id': '2330'},
            sort=[('date', -1)]
        )
        print(f'   - 流通股數查詢: {"✅" if stock_info_result else "❌"}')
        if stock_info_result:
            print(f'     outstanding_shares: {stock_info_result.get("outstanding_shares")}')
            
except Exception as e:
    print(f'❌ 錯誤: {e}')
    import traceback
    traceback.print_exc()

# 計算 PB
print('\n計算 PB Ratio...')
try:
    pb = value_factors.calculate_pb_ratio('2330', test_date)
    if pb:
        print(f'✅ PB Ratio = {pb:.2f}')
    else:
        print('❌ PB Ratio = None')
except Exception as e:
    print(f'❌ 錯誤: {e}')

# 計算 ROE
print('\n計算 ROE...')
try:
    roe = quality_factors.calculate_roe('2330', test_date)
    if roe:
        print(f'✅ ROE = {roe:.2f}%')
    else:
        print('❌ ROE = None')
except Exception as e:
    print(f'❌ 錯誤: {e}')

# 計算 ROA
print('\n計算 ROA...')
try:
    roa = quality_factors.calculate_roa('2330', test_date)
    if roa:
        print(f'✅ ROA = {roa:.2f}%')
    else:
        print('❌ ROA = None')
except Exception as e:
    print(f'❌ 錯誤: {e}')

print('\n' + '='*80)
print('診斷完成')
print('='*80)

client.close()
