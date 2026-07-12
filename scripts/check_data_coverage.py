#!/usr/bin/env python3
"""检查数据覆盖情况"""

from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

price_stocks = set(db.stock_price.distinct('stock_id'))
factor_stocks = set(db.stock_factors.distinct('symbol'))

print('=== 數據覆蓋分析 ===')
print(f'有價格數據的股票: {len(price_stocks)} 支')
print(f'有因子數據的股票: {len(factor_stocks)} 支')
print()
print(f'有因子但無價格: {len(factor_stocks - price_stocks)} 支')
print(f'有價格但無因子: {len(price_stocks - factor_stocks)} 支')
print(f'兩者都有: {len(price_stocks & factor_stocks)} 支')
print()
print('有價格數據的股票:', sorted(list(price_stocks)))
print()
print('v2.1 選出的股票價格數據狀況:')
for stock in ['1213', '1708', '1416', '1437', '1307', '1463', '2330', '1439', '1423', '1102']:
    has_price = stock in price_stocks
    has_factor = stock in factor_stocks
    count_2024 = db.stock_price.count_documents({
        'stock_id': stock,
        'date': {'$gte': '2024-01-01', '$lte': '2024-12-31'}
    })
    print(f'  {stock}: 價格={has_price:5}, 因子={has_factor:5}, 2024年筆數={count_2024:4}')
