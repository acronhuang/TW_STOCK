#!/usr/bin/env python3
"""验证流通股数下载覆盖率"""

from pymongo import MongoClient
from bson import Decimal128

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 统计 outstanding_shares 覆盖率
total_stocks = db.taiwan_stock_info.count_documents({})
with_shares = db.taiwan_stock_info.count_documents({
    'outstanding_shares': {'$exists': True, '$ne': None, '$gt': Decimal128('0')}
})

print("=" * 80)
print("流通股数下载验证报告")
print("=" * 80)
print(f"\ntaiwan_stock_info 统计:")
print(f"  总股票数: {total_stocks:,}")
print(f"  有流通股数: {with_shares:,}")
print(f"  覆盖率: {with_shares/total_stocks*100:.2f}%")

# 取样查看
print(f"\n成功下载的股票样本 (前10笔):")
samples = list(db.taiwan_stock_info.find(
    {'outstanding_shares': {'$exists': True, '$ne': None, '$gt': Decimal128('0')}},
    {'stock_id': 1, 'stock_name': 1, 'outstanding_shares': 1}
).limit(10))

for s in samples:
    stock_id = s.get('stock_id', 'N/A')
    stock_name = s.get('stock_name', 'N/A')
    shares = s.get('outstanding_shares')
    
    if isinstance(shares, Decimal128):
        shares_k = float(shares.to_decimal())
        print(f"  {stock_id} {stock_name}: {shares_k:,.0f} 千股 ({shares_k*1000/1e9:.2f} 十亿股)")
    else:
        print(f"  {stock_id} {stock_name}: {shares}")

# 检查主流股票
print(f"\n检查主流股票 (Top 9):")
test_stocks = ['2330', '2317', '2454', '2881', '2882', '2412', '2303', '1301', '1326']
success_count = 0

for stock_id in test_stocks:
    stock = db.taiwan_stock_info.find_one({'stock_id': stock_id})
    if stock:
        shares = stock.get('outstanding_shares')
        name = stock.get('stock_name', stock_id)
        if shares and isinstance(shares, Decimal128):
            shares_k = float(shares.to_decimal())
            print(f"  ✅ {stock_id} {name}: {shares_k:,.0f} 千股")
            success_count += 1
        else:
            print(f"  ❌ {stock_id} {name}: 无数据")
    else:
        print(f"  ❌ {stock_id}: 找不到")

print(f"\n主流股票覆盖率: {success_count}/{len(test_stocks)} ({success_count/len(test_stocks)*100:.1f}%)")

# 数据类型验证
print(f"\n数据类型验证:")
sample_with_shares = db.taiwan_stock_info.find_one({
    'outstanding_shares': {'$exists': True, '$ne': None}
})

if sample_with_shares:
    shares = sample_with_shares.get('outstanding_shares')
    print(f"  样本股票: {sample_with_shares.get('stock_id')}")
    print(f"  数据类型: {type(shares).__name__}")
    print(f"  是否 Decimal128: {isinstance(shares, Decimal128)}")
    if isinstance(shares, Decimal128):
        print(f"  ✅ 数据类型正确")
else:
    print(f"  ❌ 找不到样本")

print("\n" + "=" * 80)
print("验证完成")
print("=" * 80)
