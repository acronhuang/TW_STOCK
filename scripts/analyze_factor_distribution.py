#!/usr/bin/env python3
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== stock_factors 股票分佈分析 ===\n')

# 1. 總記錄數
total = db.stock_factors.count_documents({})
print(f'stock_factors 總記錄數: {total:,}')

# 2. 有財報的 207 支股票
financial_stocks = [
    doc['symbol'] 
    for doc in db.financial_reports.aggregate([
        {'$group': {'_id': '$symbol'}},
        {'$project': {'symbol': '$_id', '_id': 0}}
    ])
]
print(f'有財報的股票數: {len(financial_stocks)}')

# 3. stock_factors 中這 207 支股票的記錄數
factors_with_financial = db.stock_factors.count_documents({
    'symbol': {'$in': financial_stocks}
})

print(f'\nstock_factors 中有財報股票的記錄數:')
print(f'  記錄數: {factors_with_financial:,}')
print(f'  占比: {factors_with_financial/total*100:.2f}%')

# 4. 檢查 ROE 覆蓋率
roe_count = db.stock_factors.count_documents({
    'roe': {'$exists': True, '$ne': None}
})

print(f'\nstock_factors 中有 ROE 的記錄數:')
print(f'  記錄數: {roe_count:,}')
print(f'  占比: {roe_count/total*100:.2f}%')

# 5. 這兩個數字應該接近
print(f'\n【結論】:')
if abs(factors_with_financial/total - roe_count/total) < 0.02:  # 2% 容差
    print(f'  ✅ ROE 覆蓋率 ({roe_count/total*100:.1f}%) ≈ 有財報股票占比 ({factors_with_financial/total*100:.1f}%)')
    print(f'  這證明：質量因子的高覆蓋率是因為有財報的 207 支股票占了大部分 stock_factors 記錄')
else:
    print(f'  ⚠️  兩者不匹配，需要進一步調查')

# 6. 沒財報的股票記錄數
factors_without_financial = total - factors_with_financial
print(f'\nstock_factors 中沒財報股票的記錄數:')
print(f'  記錄數: {factors_without_financial:,}')
print(f'  占比: {factors_without_financial/total*100:.2f}%')

client.close()
