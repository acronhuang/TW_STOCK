#!/usr/bin/env python3
"""
檢查 TaiwanStockPER 數據是否可用
"""
from pymongo import MongoClient

db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']

print('=' * 80)
print('TaiwanStockPER 數據檢查')
print('=' * 80)

# 統計
total = db.taiwan_stock_per.count_documents({})
print(f'\ntaiwan_stock_per 總記錄數: {total:,}')

if total > 0:
    # 股票數
    stock_count = len(db.taiwan_stock_per.distinct('stock_id'))
    print(f'涵蓋股票數: {stock_count:,}')
    
    # 日期範圍
    oldest = db.taiwan_stock_per.find_one({}, sort=[('date', 1)])
    newest = db.taiwan_stock_per.find_one({}, sort=[('date', -1)])
    if oldest and newest:
        print(f'日期範圍: {oldest["date"].strftime("%Y-%m-%d")} ~ {newest["date"].strftime("%Y-%m-%d")}')
    
    # 查看樣本數據（2330 台積電）
    print('\n樣本數據（2330）:')
    docs = list(db.taiwan_stock_per.find(
        {'stock_id': '2330'},
        {'date': 1, 'PER': 1, 'PBR': 1, 'dividend_yield': 1}
    ).sort('date', -1).limit(5))
    
    for doc in docs:
        date = doc['date'].strftime('%Y-%m-%d')
        per = doc.get('PER', 'N/A')
        pbr = doc.get('PBR', 'N/A')
        div = doc.get('dividend_yield', 'N/A')
        print(f'  {date}: PE={per:>7}, PB={pbr:>7}, 殖利率={div}')
    
    # 檢查有多少記錄有有效的 PER 值
    with_per = db.taiwan_stock_per.count_documents({'PER': {'$exists': True, '$ne': None, '$gt': 0}})
    with_pbr = db.taiwan_stock_per.count_documents({'PBR': {'$exists': True, '$ne': None, '$gt': 0}})
    
    print(f'\n有效數據統計:')
    print(f'  有 PER > 0: {with_per:,} ({with_per/total*100:.1f}%)')
    print(f'  有 PBR > 0: {with_pbr:,} ({with_pbr/total*100:.1f}%)')
    
    print('\n✅ taiwan_stock_per 數據可用！')
    print('   建議：修改 value_factors.py，直接使用這些數據')
else:
    print('\n❌ taiwan_stock_per 集合為空')
    print('   需要執行：')
    print('   python3 src/downloaders/unified_downloader.py --table "個股 PER、PBR" --execute')

print('=' * 80)
