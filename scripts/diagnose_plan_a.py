#!/usr/bin/env python3
"""
診斷方案 A 執行後覆蓋率沒有提升的原因
"""

from pymongo import MongoClient
from datetime import datetime

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("=" * 80)
    print("方案 A 診斷報告")
    print("=" * 80)
    
    # 1. 檢查 stock_factors 中 PE/PB 的日期分佈
    print("\n【1. stock_factors 中價值因子的日期分佈】")
    
    pe_earliest = list(db.stock_factors.find(
        {'pe_ratio': {'$exists': True, '$ne': None}},
        {'date': 1}
    ).sort('date', 1).limit(1))
    
    pe_latest = list(db.stock_factors.find(
        {'pe_ratio': {'$exists': True, '$ne': None}},
        {'date': 1}
    ).sort('date', -1).limit(1))
    
    if pe_earliest:
        print(f"有 PE 的最早日期: {pe_earliest[0]['date'].strftime('%Y-%m-%d')}")
        print(f"有 PE 的最晚日期: {pe_latest[0]['date'].strftime('%Y-%m-%d')}")
    else:
        print("沒有 PE 數據")
    
    # 2. 檢查 2024-2025 的 PE 覆蓋率
    print("\n【2. 2024-2025 期間的覆蓋率】")
    
    total_2024_2025 = db.stock_factors.count_documents({
        'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2025, 2, 23)}
    })
    
    pe_2024_2025 = db.stock_factors.count_documents({
        'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2025, 2, 23)},
        'pe_ratio': {'$exists': True, '$ne': None}
    })
    
    pb_2024_2025 = db.stock_factors.count_documents({
        'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2025, 2, 23)},
        'pb_ratio': {'$exists': True, '$ne': None}
    })
    
    print(f"總記錄數:     {total_2024_2025:,}")
    print(f"有 PE Ratio:  {pe_2024_2025:,} ({pe_2024_2025/total_2024_2025*100:.1f}%)")
    print(f"有 PB Ratio:  {pb_2024_2025:,} ({pb_2024_2025/total_2024_2025*100:.1f}%)")
    
    # 3. 檢查 taiwan_stock_per 的日期分佈
    print("\n【3. taiwan_stock_per 的日期分佈】")
    
    per_earliest = list(db.taiwan_stock_per.find({}, {'date': 1}).sort('date', 1).limit(1))
    per_latest = list(db.taiwan_stock_per.find({}, {'date': 1}).sort('date', -1).limit(1))
    
    print(f"最早日期: {per_earliest[0]['date'].strftime('%Y-%m-%d')}")
    print(f"最晚日期: {per_latest[0]['date'].strftime('%Y-%m-%d')}")
    
    per_2024_2025 = db.taiwan_stock_per.count_documents({
        'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2025, 2, 23)}
    })
    
    per_total = db.taiwan_stock_per.count_documents({})
    
    print(f"總記錄數:           {per_total:,}")
    print(f"2024-2025 記錄數:   {per_2024_2025:,} ({per_2024_2025/per_total*100:.1f}%)")
    
    # 4. 隨機檢查幾筆數據匹配情況
    print("\n【4. 數據匹配測試】")
    
    test_cases = [
        ('2330', datetime(2024, 2, 20)),
        ('2330', datetime(2024, 6, 15)),
        ('2317', datetime(2024, 3, 10)),
    ]
    
    for symbol, date in test_cases:
        print(f"\n測試: {symbol} @ {date.strftime('%Y-%m-%d')}")
        
        # 檢查 stock_factors
        factor_doc = db.stock_factors.find_one({
            'symbol': symbol,
            'date': date
        })
        
        if factor_doc:
            pe = factor_doc.get('pe_ratio')
            pb = factor_doc.get('pb_ratio')
            print(f"  stock_factors:      PE={pe}, PB={pb}")
        else:
            print(f"  stock_factors:      無記錄")
        
        # 檢查 taiwan_stock_per
        per_doc = db.taiwan_stock_per.find_one({
            'stock_id': symbol,
            'date': date
        })
        
        if per_doc:
            per = per_doc.get('PER')
            pbr = per_doc.get('PBR')
            print(f"  taiwan_stock_per:   PER={per}, PBR={pbr}")
        else:
            print(f"  taiwan_stock_per:   無記錄")
    
    # 5. 檢查 2024-2025 期間有多少 stock_factors 記錄的日期在 taiwan_stock_per 中存在
    print("\n【5. 日期匹配分析】")
    
    # 獲取 taiwan_stock_per 中的所有日期
    per_dates = set()
    for doc in db.taiwan_stock_per.find({}, {'date': 1}):
        per_dates.add(doc['date'].strftime('%Y-%m-%d'))
    
    print(f"taiwan_stock_per 涵蓋日期數: {len(per_dates)}")
    
    # 隨機抽樣 100 筆 stock_factors (2024-2025) 看看有多少日期匹配
    sample_factors = list(db.stock_factors.find(
        {'date': {'$gte': datetime(2024, 1, 1), '$lte': datetime(2025, 2, 23)}},
        {'symbol': 1, 'date': 1}
    ).limit(100))
    
    matched = 0
    for doc in sample_factors:
        date_str = doc['date'].strftime('%Y-%m-%d')
        if date_str in per_dates:
            matched += 1
    
    print(f"抽樣 100 筆 stock_factors:")
    print(f"  日期在 taiwan_stock_per 中: {matched} ({matched/100*100:.1f}%)")
    
    # 6. 分析根本原因
    print("\n" + "=" * 80)
    print("【診斷結果】")
    print("=" * 80)
    
    if pe_2024_2025 / total_2024_2025 < 0.5:
        print("\n❌ 問題確認: 2024-2025 的價值因子覆蓋率非常低")
        print("\n可能原因:")
        print("  1. 日期不匹配: taiwan_stock_per 的日期和 stock_factors 不同步")
        print("  2. stock_id vs symbol: 欄位名稱不同可能導致查詢失敗")
        print("  3. 代碼邏輯問題: calculate_pe_ratio/pb_ratio 可能有 bug")
        print("  4. 只計算了 2024-2025，但舊數據（2020-2023）沒有重新計算")
        
        print("\n建議解決方案:")
        print("  ✓ 方案 A: 重新計算所有年份（2020-2025）的因子")
        print("  ✓ 方案 B: 檢查並修復日期匹配問題")
        print("  ✓ 方案 C: 檢查 value_factors.py 的代碼邏輯")
    else:
        print("\n✅ 2024-2025 期間覆蓋率正常")
    
    client.close()

if __name__ == '__main__':
    main()
