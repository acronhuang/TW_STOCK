#!/usr/bin/env python3
"""
檢查流通股數 (outstanding_shares) 的覆蓋率
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*80)
print('流通股數 (taiwan_stock_info) 覆蓋率檢查')
print('='*80)

# 有財報的股票
有財報 = set(db.financial_reports.distinct('symbol'))
print(f'\n有財報的股票數: {len(有財報)}')

# 有流通股數的股票
有股數 = set(db.taiwan_stock_info.distinct('stock_id'))
print(f'taiwan_stock_info 中有數據的股票: {len(有股數)}')

# 交集：既有財報又有流通股數的股票
兩者都有 = 有財報.intersection(有股數)
print(f'既有財報又有流通股數: {len(兩者都有)} ({len(兩者都有)/len(有財報)*100:.1f}%)')

# 有財報但沒流通股數的股票
缺股數 = 有財報 - 有股數
print(f'有財報但缺流通股數: {len(缺股數)} ({len(缺股數)/len(有財報)*100:.1f}%)')

if 缺股數:
    print(f'\n缺流通股數的股票（前 20 支）: {sorted(list(缺股數))[:20]}')

print()
print('='*80)
print('結論')
print('='*80)

if len(兩者都有) / len(有財報) > 0.9:
    print('✅ 流通股數數據覆蓋率良好 (>90%)')
    print('   問題應該不在流通股數')
else:
    print(f'⚠️  警告: {len(缺股數)} 支有財報的股票缺少流通股數')
    print('   這會導致無法計算 PE/PB/ROE/ROA')
    print()
    print('   建議執行:')
    print('   python3 src/downloaders/outstanding_shares_downloader.py --all --execute')

# 檢查記錄數
print()
print(f'\ntaiwan_stock_info 總記錄數: {db.taiwan_stock_info.count_documents({}):,}')
print(f'平均每支股票記錄數: {db.taiwan_stock_info.count_documents({}) / len(有股數):.1f}')

# 檢查 outstanding_shares 欄位
有股數欄位 = db.taiwan_stock_info.count_documents({'outstanding_shares': {'$exists': True, '$ne': None, '$ne': 0}})
print(f'\n有 outstanding_shares 欄位: {有股數欄位:,}')
print(f'覆蓋率: {有股數欄位 / db.taiwan_stock_info.count_documents({})*100:.1f}%')

client.close()
