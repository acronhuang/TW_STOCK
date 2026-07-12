#!/usr/bin/env python3
"""P0 精度快速診斷"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128

def diagnose():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("="*80)
    print("P0 精度診斷報告")
    print("="*80)
    
    # 檢查 dividend_detail
    print("\n[1] dividend_detail.cash_earnings_distribution:")
    div = db.dividend_detail.find_one({'cash_earnings_distribution': {'$exists': True, '$ne': None}})
    if div:
        val = div.get('cash_earnings_distribution')
        is_decimal = isinstance(val, Decimal128)
        print(f"  類型: {type(val).__name__}")
        print(f"  是 Decimal128? {is_decimal}")
        if not is_decimal:
            print("  ❌ 不是 Decimal128 - 需要執行 P0 遷移")
        else:
            print("  ✅ 已是 Decimal128")
    
    # 檢查 stock_price
    print("\n[2] stock_price.close:")
    price = db.stock_price.find_one({'close': {'$exists': True}})
    if price:
        val = price.get('close')
        is_decimal = isinstance(val, Decimal128)
        print(f"  類型: {type(val).__name__}")
        print(f"  是 Decimal128? {is_decimal}")
        if not is_decimal:
            print("  ❌ 不是 Decimal128 - 需要執行 P0 遷移")
        else:
            print("  ✅ 已是 Decimal128")
    
    # 統計類型分佈
    print("\n[3] 類型分佈統計 (前1000筆):")
    types = {}
    for doc in db.dividend_detail.find().limit(1000):
        val = doc.get('cash_earnings_distribution')
        if val is not None:
            t = type(val).__name__
            types[t] = types.get(t, 0) + 1
    
    for t, count in types.items():
        print(f"  {t}: {count}")
    
    print("\n" + "="*80)
    
    # 結論
    has_float = 'float' in types or 'double' in types
    if has_float:
        print("❌ 發現 Float/Double 類型 - 立即執行 P0 強制遷移")
        print("   指令: echo 'YES' | python3 src/migrations/p0_force_decimal_migration.py --execute")
    else:
        print("✅ 全部為 Decimal128 - P0 已完成")
    
    print("="*80)

if __name__ == '__main__':
    diagnose()
