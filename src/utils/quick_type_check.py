#!/usr/bin/env python3
"""快速精度驗證工具"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128

def check_types():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("="*80)
    print("精度狀態快速驗證")
    print("="*80)
    
    # 檢查 dividend_detail
    print("\n[1] dividend_detail 集合:")
    div = db.dividend_detail.find_one({'cash_earnings_distribution': {'$exists': True, '$ne': None}})
    if div and 'cash_earnings_distribution' in div:
        val = div['cash_earnings_distribution']
        print(f"  欄位: cash_earnings_distribution")
        print(f"  類型: {type(val).__name__}")
        print(f"  值: {val}")
        print(f"  是 Decimal128? {isinstance(val, Decimal128)}")
    else:
        print("  ⚠️  沒有找到有效數據")
    
    # 檢查 stock_price
    print("\n[2] stock_price 集合:")
    price = db.stock_price.find_one({'close': {'$exists': True}})
    if price and 'close' in price:
        val = price['close']
        print(f"  欄位: close")
        print(f"  類型: {type(val).__name__}")
        print(f"  值: {val}")
        print(f"  是 Decimal128? {isinstance(val, Decimal128)}")
    else:
        print("  ⚠️  沒有找到有效數據")
    
    # 統計類型分佈
    print("\n[3] dividend_detail 類型統計 (前1000筆):")
    pipeline = [
        {'$limit': 1000},
        {'$project': {
            'cash_type': {'$type': '$cash_earnings_distribution'}
        }},
        {'$group': {
            '_id': '$cash_type',
            'count': {'$sum': 1}
        }}
    ]
    
    for result in db.dividend_detail.aggregate(pipeline):
        print(f"  {result['_id']}: {result['count']} 筆")
    
    print("\n" + "="*80)

if __name__ == '__main__':
    check_types()
