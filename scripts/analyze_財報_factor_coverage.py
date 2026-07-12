#!/usr/bin/env python3
"""
分析有財報股票的因子覆蓋率
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 有財報的股票
有財報 = set(db.financial_reports.distinct('symbol')).union(
    set(db.financial_statements.distinct('symbol'))
)

print('針對有財報的 212 支股票，檢查因子計算覆蓋率:')
print('='*80)

# 這 212 支股票的價格記錄數
這些股票的價格記錄 = db.stock_price.count_documents({
    'symbol': {'$in': list(有財報)}
})

# 這 212 支股票的因子記錄數
這些股票的因子記錄 = db.stock_factors.count_documents({
    'symbol': {'$in': list(有財報)}
})

# 有 PE ratio 的因子記錄
這些股票有PE = db.stock_factors.count_documents({
    'symbol': {'$in': list(有財報)},
    'pe_ratio': {'$ne': None}
})

# 有 ROE 的因子記錄
這些股票有ROE = db.stock_factors.count_documents({
    'symbol': {'$in': list(有財報)},
    'roe': {'$ne': None}
})

print(f'有財報股票的價格記錄數: {這些股票的價格記錄:,}')
print(f'有財報股票的因子記錄數: {這些股票的因子記錄:,}')
print(f'  → 因子記錄覆蓋率: {這些股票的因子記錄/這些股票的價格記錄*100:.1f}%')
print()
print(f'有 PE ratio 的記錄: {這些股票有PE:,}')
print(f'  → PE/PB 覆蓋率: {這些股票有PE/這些股票的因子記錄*100:.1f}%')
print(f'有 ROE 的記錄: {這些股票有ROE:,}')
print(f'  → ROE 覆蓋率: {這些股票有ROE/這些股票的因子記錄*100:.1f}%')
print('='*80)

# 結論
print()
print('【結論】:')
if 這些股票有PE / 這些股票的因子記錄 > 0.5:
    print('✅ 有財報的股票中，超過 50% 的因子記錄有 PE/PB 值')
    print('   這是正常的！因為：')
    print('   - 財報是季度發布（一年 4 次）')
    print('   - 但每個交易日都會計算動能因子')
    print('   - 因此動能因子記錄會遠多於價值/質量因子')
else:
    print('⚠️  即使有財報，PE/PB 覆蓋率仍然很低')
    print('   可能原因：因子計算邏輯有問題')

client.close()
