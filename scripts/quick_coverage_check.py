#!/usr/bin/env python3
"""
快速檢查因子覆蓋率（修正版）
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

price_records = db.stock_price.count_documents({})
factor_records = db.stock_factors.count_documents({})
momentum_count = db.stock_factors.count_documents({'return_1m': {'$exists': True}})
value_count = db.stock_factors.count_documents({'pe_ratio': {'$exists': True}})
quality_count = db.stock_factors.count_documents({'roe': {'$exists': True}})

print('=' * 80)
print('因子覆蓋率檢查（修正版）')
print('=' * 80)
print(f'價格記錄數: {price_records:,} (基準)')
print(f'因子記錄數: {factor_records:,}')
print(f'總覆蓋率:   {factor_records/price_records*100:.2f}%')
print()
print(f'動能因子:   {momentum_count:,} ({momentum_count/price_records*100:.2f}%)')
print(f'價值因子:   {value_count:,} ({value_count/price_records*100:.2f}%)')
print(f'質量因子:   {quality_count:,} ({quality_count/price_records*100:.2f}%)')
print('=' * 80)
print()

# 評估
if factor_records / price_records >= 0.80:
    print('✅ 總覆蓋率已達 80%+ 目標！')
elif momentum_count / price_records >= 0.80:
    print('✅ 動能因子已達 80%+ 覆蓋率')
    print('⚠️  價值和質量因子覆蓋率較低（需要財報數據）')
else:
    print('⚠️  覆蓋率未達目標')
    
print()
print('說明：')
print('• 動能因子只需價格數據，覆蓋率較高')
print('• 價值/質量因子需要財報數據（季度發布），覆蓋率較低')
print('• 多因子策略可正常運作（動能權重 50%）')
print('=' * 80)

client.close()
