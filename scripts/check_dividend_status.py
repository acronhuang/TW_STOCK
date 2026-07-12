#!/usr/bin/env python3
"""
检查当前股利数据状态
"""
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('='*60)
print('当前股利数据状态')
print('='*60)

# dividend_results 集合
dividend_count = db.dividend_results.count_documents({})
dividend_stocks = db.dividend_results.distinct('symbol')
print(f'\n📊 dividend_results 集合:')
print(f'  记录数: {dividend_count:,} 笔')
print(f'  覆盖股票: {len(dividend_stocks)} 档')
if len(dividend_stocks) <= 20:
    print(f'  股票列表: {", ".join(sorted(dividend_stocks))}')

# dividend_detail 集合
if 'dividend_detail' in db.list_collection_names():
    detail_count = db.dividend_detail.count_documents({})
    detail_stocks = db.dividend_detail.distinct('stock_id')
    print(f'\n📊 dividend_detail 集合:')
    print(f'  记录数: {detail_count:,} 笔')
    print(f'  覆盖股票: {len(detail_stocks)} 档')
else:
    print(f'\n📊 dividend_detail 集合: 不存在')

# 总股票数
total_stocks = db.tickers.count_documents({})
print(f'\n📈 总股票数: {total_stocks:,} 档')
print(f'覆盖率: {len(dividend_stocks)/total_stocks*100:.2f}%')

# 显示样本数据
print(f'\n📋 最近 3 笔股利记录:')
for record in db.dividend_results.find({}).sort('date', -1).limit(3):
    symbol = record.get('symbol') or record.get('stock_id')
    date = record.get('date')
    print(f'  {symbol} - {date}')

client.close()
print('\n✅ 检查完成！')
