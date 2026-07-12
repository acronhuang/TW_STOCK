#!/usr/bin/env python3
"""
診斷動能因子覆蓋率下降的原因
從 81.77% 下降到 55.7%
"""

from pymongo import MongoClient
from datetime import datetime

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("=" * 80)
    print("動能因子覆蓋率診斷")
    print("=" * 80)
    
    # 1. 檢查 stock_price 和 stock_factors 的記錄數
    print("\n【1. 數據基礎】")
    
    price_total = db.stock_price.count_documents({})
    factor_total = db.stock_factors.count_documents({})
    
    print(f"stock_price 總記錄數:  {price_total:,}")
    print(f"stock_factors 總記錄數: {factor_total:,}")
    print(f"因子計算覆蓋率:        {factor_total/price_total*100:.2f}%")
    
    # 2. 檢查各年份的動能因子覆蓋率
    print("\n【2. 各年份動能因子覆蓋率】")
    
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    
    for year in years:
        start = datetime(year, 1, 1)
        end = datetime(year+1, 1, 1) if year < 2025 else datetime(2025, 3, 1)
        
        # stock_factors 總記錄
        factor_count = db.stock_factors.count_documents({
            'date': {'$gte': start, '$lt': end}
        })
        
        # 有 return_1m 的記錄
        return_1m = db.stock_factors.count_documents({
            'date': {'$gte': start, '$lt': end},
            'return_1m': {'$exists': True, '$ne': None}
        })
        
        # 有 return_3m 的記錄
        return_3m = db.stock_factors.count_documents({
            'date': {'$gte': start, '$lt': end},
            'return_3m': {'$exists': True, '$ne': None}
        })
        
        # 有 return_6m 的記錄
        return_6m = db.stock_factors.count_documents({
            'date': {'$gte': start, '$lt': end},
            'return_6m': {'$exists': True, '$ne': None}
        })
        
        coverage_1m = (return_1m/factor_count*100) if factor_count > 0 else 0
        coverage_3m = (return_3m/factor_count*100) if factor_count > 0 else 0
        coverage_6m = (return_6m/factor_count*100) if factor_count > 0 else 0
        
        print(f"\n{year}:")
        print(f"  因子記錄數:    {factor_count:,}")
        print(f"  return_1m:     {return_1m:,} ({coverage_1m:.2f}%)")
        print(f"  return_3m:     {return_3m:,} ({coverage_3m:.2f}%)")
        print(f"  return_6m:     {return_6m:,} ({coverage_6m:.2f}%)")
    
    # 3. 檢查整體覆蓋率
    print("\n【3. 整體動能因子覆蓋率】")
    
    return_1m_total = db.stock_factors.count_documents({
        'return_1m': {'$exists': True, '$ne': None}
    })
    
    return_3m_total = db.stock_factors.count_documents({
        'return_3m': {'$exists': True, '$ne': None}
    })
    
    return_6m_total = db.stock_factors.count_documents({
        'return_6m': {'$exists': True, '$ne': None}
    })
    
    print(f"return_1m: {return_1m_total:,} / {factor_total:,} = {return_1m_total/factor_total*100:.2f}%")
    print(f"return_3m: {return_3m_total:,} / {factor_total:,} = {return_3m_total/factor_total*100:.2f}%")
    print(f"return_6m: {return_6m_total:,} / {factor_total:,} = {return_6m_total/factor_total*100:.2f}%")
    
    # 4. 抽樣檢查動能因子的值
    print("\n【4. 抽樣檢查（前 10 筆）】")
    
    samples = list(db.stock_factors.find({}).limit(10))
    
    for i, doc in enumerate(samples, 1):
        symbol = doc.get('symbol')
        date = doc.get('date').strftime('%Y-%m-%d')
        r1m = doc.get('return_1m')
        r3m = doc.get('return_3m')
        r6m = doc.get('return_6m')
        print(f"  {i}. {symbol} @ {date}: 1M={r1m}, 3M={r3m}, 6M={r6m}")
    
    # 5. 比較舊覆蓋率（假設是 81.77%）和新覆蓋率
    print("\n" + "=" * 80)
    print("【診斷結論】")
    print("=" * 80)
    
    current_coverage = return_1m_total / factor_total * 100
    old_coverage = 81.77
    
    print(f"\n舊覆蓋率（報告中）: {old_coverage:.2f}%")
    print(f"新覆蓋率（當前）:   {current_coverage:.2f}%")
    print(f"下降幅度:          {old_coverage - current_coverage:.2f} 個百分點")
    
    if current_coverage < old_coverage:
        print("\n可能原因:")
        print("  1. 重新計算時邏輯改變，導致某些記錄的動能因子變為 None")
        print("  2. 計算時缺少足夠的歷史價格數據（需要 1/3/6 個月前的價格）")
        print("  3. 某些股票在早期時間段沒有足夠的歷史數據")
        print("  4. 驗證報告中的 81.77% 可能是針對特定日期範圍的")
        
        # 檢查是否有特定日期範圍覆蓋率較高
        print("\n檢查 2023-2024 期間的覆蓋率:")
        factor_2023_2024 = db.stock_factors.count_documents({
            'date': {'$gte': datetime(2023, 1, 1), '$lt': datetime(2025, 1, 1)}
        })
        return_1m_2023_2024 = db.stock_factors.count_documents({
            'date': {'$gte': datetime(2023, 1, 1), '$lt': datetime(2025, 1, 1)},
            'return_1m': {'$exists': True, '$ne': None}
        })
        coverage_2023_2024 = (return_1m_2023_2024/factor_2023_2024*100) if factor_2023_2024 > 0 else 0
        print(f"  2023-2024: {return_1m_2023_2024:,} / {factor_2023_2024:,} = {coverage_2023_2024:.2f}%")
    else:
        print("\n✅ 覆蓋率符合預期")
    
    client.close()

if __name__ == '__main__':
    main()
