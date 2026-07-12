#!/usr/bin/env python3
"""
從 tickers 集合更新 stocks 集合的公司名稱
"""

from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print("="*60)
print("更新 stocks 集合的公司名稱")
print("="*60)

# 獲取所有有名稱的 tickers
tickers_with_names = list(db.tickers.find({'name': {'$exists': True, '$ne': ''}}))

print(f"\n找到 {len(tickers_with_names)} 支股票有名稱資料")

updated_count = 0
not_found_count = 0

for ticker in tickers_with_names:
    symbol = ticker['symbol']
    name = ticker['name']
    
    # 更新 stocks 集合
    result = db.stocks.update_one(
        {'symbol': symbol},
        {
            '$set': {
                'name': name,
                'updatedAt': ticker.get('updatedAt')
            }
        },
        upsert=True
    )
    
    if result.modified_count > 0 or result.upserted_id:
        updated_count += 1
        if updated_count <= 10:
            print(f"  ✓ {symbol}: {name}")

print(f"\n{'='*60}")
print(f"完成！更新 {updated_count} 支股票的名稱")
print(f"{'='*60}")

# 驗證關鍵股票
print("\n驗證關鍵股票:")
test_symbols = ['2330', '2317', '2454', '1101', '1216', '1301']
for symbol in test_symbols:
    stock = db.stocks.find_one({'symbol': symbol})
    if stock:
        print(f"  {symbol}: {stock.get('name', 'N/A')}")
