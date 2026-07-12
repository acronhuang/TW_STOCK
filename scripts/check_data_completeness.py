#!/usr/bin/env python3
"""檢查數據完整度"""

from pymongo import MongoClient
import os
import json

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*70)
print('數據完整度報告')
print('='*70)
print()

# 獲取各數據集的股票數
collections = {
    'stock_price': 'stock_id',
    'financial_reports': 'symbol',
    'taiwan_stock_per': 'stock_id',
    'dividend': 'stock_id',
    'institutional_holdings': 'stock_id',
    'institutional_trading': 'stock_id'
}

results = {}
for name, field in collections.items():
    stocks = [s for s in db[name].distinct(field) if s]
    count = db[name].count_documents({})
    results[name] = {'stocks': len(stocks), 'records': count}

all_stocks = [s for s in db.stock_list.distinct('stock_id') if s]
total = len(all_stocks)

print(f'總股票數: {total} 支\n')
print('各數據集狀況:')
print('-'*70)
print(f'{"數據集":<25} {"股票數":>10} {"完整度":>10} {"記錄數":>15}')
print('-'*70)

for name, data in results.items():
    percentage = data['stocks'] / total * 100 if total > 0 else 0
    status = '✓' if percentage > 90 else '⚠️' if percentage > 10 else '✗'
    print(f'{status} {name:<23} {data["stocks"]:>10} {percentage:>9.1f}% {data["records"]:>15,}')

print('='*70)
print()

# 檢查增量同步進度
progress_file = 'logs/finmind_sync_progress.json'
if os.path.exists(progress_file):
    with open(progress_file) as f:
        progress = json.load(f)
    print('增量同步進度:')
    print(f'  最後同步: {progress.get("last_sync", "N/A")}')
    print(f'  已同步: {progress.get("total_synced", 0)} 支')
    print()

# 說明
print('='*70)
print('說明')
print('='*70)
print()
print('當前狀況：')
print('  • stock_price: 只有 40 支股票（之前部分下載）')
print('  • 原因：FinMind API 達到請求上限')
print()
print('解決方案：')
print('  ✓ 已設置每小時增量同步（自動補齊數據）')
print('  • 每小時同步 50 支股票')
print('  • 預計 2.5 天完成 stock_price（3065 支）')
print()
print('Cron Job 狀態：')
print('  • 已設置：每小時 00 分執行')
print('  • 下次執行：查看 crontab -l')
print()
