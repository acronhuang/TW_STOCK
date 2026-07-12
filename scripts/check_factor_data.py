#!/usr/bin/env python3
"""
檢查因子數據完整性
"""
from pymongo import MongoClient
from datetime import datetime
import pandas as pd

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("=" * 80)
    print("因子數據完整性檢查")
    print("=" * 80)
    
    # 統計總數
    total = db.stock_factors.count_documents({})
    print(f"\n總記錄數: {total}")
    
    # 統計各因子的完整度
    print("\n因子完整度統計（2024年）:")
    print("-" * 80)
    
    factors = [
        'pe_ratio', 'pb_ratio', 'dividend_yield', 'earnings_yield',
        'return_1m', 'return_3m', 'return_6m', 'return_12m', 'rsi_14', 'volatility_30d',
        'roe', 'roa', 'profit_margin', 'operating_margin', 'current_ratio', 'debt_ratio'
    ]
    
    results = []
    for factor in factors:
        count = db.stock_factors.count_documents({
            'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2024, 12, 31)},
            factor: {'$ne': None}
        })
        coverage = (count / total * 100) if total > 0 else 0
        results.append({
            'Factor': factor,
            'Count': count,
            'Coverage': f"{coverage:.1f}%"
        })
    
    df = pd.DataFrame(results)
    print(df.to_string(index=False))
    
    # 查看樣本數據
    print("\n" + "=" * 80)
    print("樣本數據（2330, 最近5天）:")
    print("-" * 80)
    
    cursor = db.stock_factors.find(
        {'symbol': '2330'},
        {'_id': 0, 'symbol': 1, 'date': 1, 'pe_ratio': 1, 'pb_ratio': 1, 
         'roe': 1, 'return_3m': 1, 'rsi_14': 1}
    ).sort('date', -1).limit(5)
    
    for doc in cursor:
        print(f"\nDate: {doc.get('date', 'N/A')}")
        print(f"  PE Ratio: {doc.get('pe_ratio', 'N/A')}")
        print(f"  PB Ratio: {doc.get('pb_ratio', 'N/A')}")
        print(f"  ROE: {doc.get('roe', 'N/A')}")
        print(f"  Return 3M: {doc.get('return_3m', 'N/A')}")
        print(f"  RSI 14: {doc.get('rsi_14', 'N/A')}")
    
    # 檢查 stock_price 中的 PE/PB 數據
    print("\n" + "=" * 80)
    print("檢查 stock_price 集合中的 PE/PB 數據:")
    print("-" * 80)
    
    sample = db.stock_price.find_one(
        {'symbol': '2330', 'pe_ratio': {'$ne': None}},
        {'_id': 0, 'date': 1, 'symbol': 1, 'close': 1, 'pe_ratio': 1, 'pb_ratio': 1}
    )
    
    if sample:
        print("\n✅ stock_price 集合中有 PE/PB 數據！")
        print(f"範例: {sample}")
        
        # 統計有 PE 數據的記錄數
        pe_count = db.stock_price.count_documents({
            'date': {'$gte': datetime(2024, 1, 1)},
            'pe_ratio': {'$ne': None}
        })
        print(f"\n2024年有 PE 數據的記錄數: {pe_count}")
    else:
        print("\n⚠️  stock_price 集合中沒有 PE/PB 數據")
    
    print("\n" + "=" * 80)
    print("診斷建議:")
    print("-" * 80)
    
    if df[df['Factor'].str.contains('return|rsi|volatility')]['Count'].sum() > 0:
        print("✅ 動能因子 (return, rsi, volatility) 計算正常")
    else:
        print("❌ 動能因子缺失")
    
    if df[df['Factor'].str.contains('pe|pb|dividend|earnings')]['Count'].sum() > 0:
        print("✅ 價值因子 (PE, PB, dividend) 計算正常")
    else:
        print("⚠️  價值因子缺失 - 需要從 stock_price 或 financial_reports 取得")
    
    if df[df['Factor'].str.contains('roe|roa|margin|ratio')]['Count'].sum() > 0:
        print("✅ 質量因子 (ROE, ROA, margins) 計算正常")
    else:
        print("⚠️  質量因子缺失 - 需要從 financial_reports 取得")
    
    client.close()

if __name__ == '__main__':
    main()
