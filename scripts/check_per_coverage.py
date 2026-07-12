#!/usr/bin/env python3
"""檢查 TaiwanStockPER 數據覆蓋率"""
from pymongo import MongoClient

db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']

# 統計
total_records = db.taiwan_stock_per.count_documents({})
stock_count = len(db.taiwan_stock_per.distinct('stock_id'))
with_per = db.taiwan_stock_per.count_documents({'PER': {'$exists': True, '$ne': None, '$ne': 0}})
with_pbr = db.taiwan_stock_per.count_documents({'PBR': {'$exists': True, '$ne': None, '$ne': 0}})

# 有財報的股票
有財報股票 = set(db.financial_reports.distinct('symbol'))
有PER股票 = set(db.taiwan_stock_per.distinct('stock_id'))
兩者都有 = 有財報股票.intersection(有PER股票)

print('=' * 60)
print('TaiwanStockPER 數據現狀')
print('=' * 60)
print(f'\n總記錄數:     {total_records:>8,}')
print(f'涵蓋股票:     {stock_count:>8,}')
print(f'有效 PER:     {with_per:>8,} ({with_per/total_records*100:.1f}%)')
print(f'有效 PBR:     {with_pbr:>8,} ({with_pbr/total_records*100:.1f}%)')

print(f'\n有財報股票:   {len(有財報股票):>8,}')
print(f'有PER股票:    {len(有PER股票):>8,}')
print(f'兩者都有:     {len(兩者都有):>8,} ({len(兩者都有)/len(有財報股票)*100:.1f}%)')

# 檢查日期範圍
oldest = db.taiwan_stock_per.find_one({}, sort=[('date', 1)])
newest = db.taiwan_stock_per.find_one({}, sort=[('date', -1)])
if oldest and newest:
    print(f'\n日期範圍:     {oldest["date"].strftime("%Y-%m-%d")} ~ {newest["date"].strftime("%Y-%m-%d")}')

print('=' * 60)

if len(兩者都有) / len(有財報股票) > 0.8:
    print('\n✅ PE/PB 覆蓋率良好 (>80%)')
    print('   可以直接修改 value_factors.py 使用這些數據\n')
else:
    缺PER = 有財報股票 - 有PER股票
    print(f'\n⚠️  還有 {len(缺PER)} 支有財報股票缺 PE/PB 數據')
    print(f'   建議下載這些股票: {sorted(list(缺PER))[:10]}...\n')
