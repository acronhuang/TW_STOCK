#!/usr/bin/env python3
"""
測試還原後的 value_factors.py (使用 outstanding_shares)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from datetime import datetime
from src.factors.value_factors import ValueFactors

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    calculator = ValueFactors(db)
    
    print("=" * 80)
    print("測試還原後的 value_factors.py (使用 outstanding_shares)")
    print("=" * 80)
    
    test_symbol = '2330'
    test_date = datetime(2024, 2, 20)
    
    print(f"\n測試股票: {test_symbol}")
    print(f"測試日期: {test_date.strftime('%Y-%m-%d')}")
    
    # 1. 檢查 taiwan_stock_info 中的 outstanding_shares
    print("\n【1. 檢查數據來源】")
    stock_info = db.taiwan_stock_info.find_one(
        {'stock_id': test_symbol},
        sort=[('date', -1)]
    )
    
    if stock_info:
        outstanding_shares = stock_info.get('outstanding_shares')
        print(f"✓ taiwan_stock_info 有數據")
        print(f"  outstanding_shares: {outstanding_shares}")
        print(f"  日期: {stock_info.get('date')}")
    else:
        print(f"✗ taiwan_stock_info 沒有數據")
        return
    
    # 2. 測試 PE ratio
    print("\n【2. 測試 PE Ratio】")
    pe = calculator.calculate_pe_ratio(test_symbol, test_date)
    print(f"PE Ratio: {pe}")
    
    if pe:
        print("✅ PE 計算成功")
    else:
        print("❌ PE 計算失敗")
    
    # 3. 測試 PB ratio
    print("\n【3. 測試 PB Ratio】")
    pb = calculator.calculate_pb_ratio(test_symbol, test_date)
    print(f"PB Ratio: {pb}")
    
    if pb:
        print("✅ PB 計算成功")
    else:
        print("❌ PB 計算失敗")
    
    # 4. 對比 taiwan_stock_per 的值（參考用）
    print("\n【4. 參考：taiwan_stock_per 的值】")
    per_doc = db.taiwan_stock_per.find_one({
        'stock_id': test_symbol,
        'date': test_date
    })
    
    if per_doc:
        print(f"taiwan_stock_per.PER: {per_doc.get('PER')}")
        print(f"taiwan_stock_per.PBR: {per_doc.get('PBR')}")
        
        if pe and per_doc.get('PER'):
            diff_pe = abs(pe - per_doc.get('PER'))
            print(f"\nPE 差異: {diff_pe:.2f}")
            if diff_pe < 1:
                print("✅ PE 值接近 FinMind 官方值")
            else:
                print(f"⚠️  PE 值與 FinMind 有差異 ({diff_pe:.2f})")
    
    print("\n" + "=" * 80)
    if pe and pb:
        print("✅ 還原後的 value_factors.py 工作正常")
    else:
        print("❌ 還原後的 value_factors.py 有問題")
    print("=" * 80)
    
    client.close()

if __name__ == '__main__':
    main()
