#!/usr/bin/env python3
"""驗證因子覆蓋率提升（方案 A 執行後）"""
from pymongo import MongoClient
from datetime import datetime

db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']

print('=' * 70)
print('因子覆蓋率驗證報告（方案 A: 使用 TaiwanStockPER）')
print('=' * 70)

# 1. 數據基礎統計
price_records = db.stock_price.count_documents({})
factor_records = db.stock_factors.count_documents({})

print(f'\n【數據基礎】')
print(f'價格記錄數:   {price_records:>10,}')
print(f'因子記錄數:   {factor_records:>10,}')
print(f'總體覆蓋率:   {factor_records/price_records*100:>9.1f}%')

# 2. 動能因子覆蓋率（作為對照組）
momentum_count = db.stock_factors.count_documents({
    'return_1m': {'$exists': True, '$ne': None}
})
print(f'\n【動能因子】（對照組）')
print(f'有 return_1m: {momentum_count:>10,} ({momentum_count/factor_records*100:.1f}%)')

# 3. 價值因子覆蓋率（舊方法：using outstanding_shares）
pe_count = db.stock_factors.count_documents({
    'pe_ratio': {'$exists': True, '$ne': None}
})
pb_count = db.stock_factors.count_documents({
    'pb_ratio': {'$exists': True, '$ne': None}
})

print(f'\n【價值因子】（使用 outstanding_shares）')
print(f'有 PE Ratio:  {pe_count:>10,} ({pe_count/factor_records*100:.1f}%)')
print(f'有 PB Ratio:  {pb_count:>10,} ({pb_count/factor_records*100:.1f}%)')

# 4. 質量因子覆蓋率
roe_count = db.stock_factors.count_documents({
    'roe': {'$exists': True, '$ne': None}
})
roa_count = db.stock_factors.count_documents({
    'roa': {'$exists': True, '$ne': None}
})

print(f'\n【質量因子】')
print(f'有 ROE:       {roe_count:>10,} ({roe_count/factor_records*100:.1f}%)')
print(f'有 ROA:       {roa_count:>10,} ({roa_count/factor_records*100:.1f}%)')

# 5. TaiwanStockPER 數據統計
per_records = db.taiwan_stock_per.count_documents({})
per_stocks = len(db.taiwan_stock_per.distinct('stock_id'))
有財報股票 = len(db.financial_reports.distinct('symbol'))

print(f'\n【TaiwanStockPER 數據源】')
print(f'PER 總記錄:   {per_records:>10,}')
print(f'涵蓋股票數:   {per_stocks:>10,}')
print(f'有財報股票:   {有財報股票:>10,}')
print(f'覆蓋率:       {per_stocks/有財報股票*100:>9.1f}%')

# 6. 改進效果評估
print('\n' + '=' * 70)
print('改進效果評估')
print('=' * 70)

# 假設之前的覆蓋率（從診斷報告）
原價值因子覆蓋率 = 7.47  # %
原質量因子覆蓋率 = 7.86  # %

價值因子改進 = pe_count/price_records*100 - 原價值因子覆蓋率
質量改進預估 = pb_count/price_records*100 - 原質量因子覆蓋率

print(f'\n價值因子 PE Ratio:')
print(f'  原覆蓋率:   {原價值因子覆蓋率:>6.1f}%')
print(f'  新覆蓋率:   {pe_count/price_records*100:>6.1f}%')
print(f'  改進:       {價值因子改進:>+6.1f} 個百分點')

print(f'\n價值因子 PB Ratio:')
print(f'  原覆蓋率:   {原價值因子覆蓋率:>6.1f}%')
print(f'  新覆蓋率:   {pb_count/price_records*100:>6.1f}%')
print(f'  改進:       {質量改進預估:>+6.1f} 個百分點')

# 7. 目標達成評估
print('\n' + '=' * 70)
print('目標達成評估')
print('=' * 70)

目標覆蓋率 = 50  # %
pe_達標 = pe_count/price_records*100 >= 目標覆蓋率
pb_達標 = pb_count/price_records*100 >= 目標覆蓋率

print(f'\n目標: 價值因子覆蓋率 ≥ {目標覆蓋率}%')
print(f'  PE Ratio: {pe_count/price_records*100:.1f}% {"✅ 達標" if pe_達標 else "❌ 未達標"}')
print(f'  PB Ratio: {pb_count/price_records*100:.1f}% {"✅ 達標" if pb_達標 else "❌ 未達標"}')

if pe_達標 and pb_達標:
    print(f'\n🎉 方案 A 執行成功！價值因子覆蓋率已提升至 {目標覆蓋率}%+')
elif pe_count/price_records*100 > 20 or pb_count/price_records*100 > 20:
    print(f'\n✅ 方案 A 部分成功！覆蓋率有顯著提升')
    print(f'   建議：繼續下載更多歷史 PE/PB 數據（2020-2023 年）')
else:
    print(f'\n⚠️  方案 A 執行中，覆蓋率提升有限')
    print(f'   可能原因：')
    print(f'   1. 因子重新計算尚未完成')
    print(f'   2. 需要計算更多年份的數據')

print('\n' + '=' * 70)
