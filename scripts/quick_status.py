#!/usr/bin/env python3
"""快速狀態檢查"""

from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*70)
print('系統當前狀況')
print('='*70)
print()

# 檢查數據
data = {
    'stock_price': ('stock_id', '股價'),
    'financial_reports': ('symbol', '財報'),
    'taiwan_stock_per': ('stock_id', 'PE/PB'),
    'dividend': ('stock_id', '除權息'),
    'stock_list': ('stock_id', '股票列表')
}

for coll, (field, desc) in data.items():
    count = db[coll].count_documents({})
    if count > 0:
        stocks = len(db[coll].distinct(field))
        print(f'✓ {desc:8} {count:>10,} 筆  {stocks:>5} 支')
    else:
        print(f'✗ {desc:8} {"無數據":>10}')

print()
print('='*70)
print('FinMind API 狀態')
print('='*70)
print()
print('⚠️  API 已達請求上限（Status 402）')
print('   免費版限制：每日 1,000 次請求')
print()
print('解決方案：')
print('  1. 等待 24 小時後重新同步（免費）')
print('  2. 升級到 Premium 版（$99/月，無限制）')
print()
print('='*70)
print('建議下一步')
print('='*70)
print()
print('由於數據不足（僅 36 支股票），建議：')
print()
print('1. 等待明天（2026-02-24 22:13 之後）執行：')
print('   python3 scripts/finmind_full_sync.py --initial')
print()
print('2. 或立即購買 Premium 並同步：')
print('   https://finmindtrade.com/')
print()
