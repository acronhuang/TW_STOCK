#!/usr/bin/env python3
"""
重新計算所有股票的因子數據
"""
import sys
from pathlib import Path

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from factors import FactorLibrary

def recalculate_factors():
    """重新計算所有因子"""
    print("=" * 80)
    print("重新計算所有股票的因子數據")
    print("=" * 80)
    
    # 建立因子庫
    factor_lib = FactorLibrary()
    
    # 連接資料庫
    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 獲取一般股票代碼（排除 ETF/權證/0開頭）
    all_syms = db.stock_price.distinct('symbol')
    symbols = sorted(s for s in all_syms if s.isdigit() and len(s) == 4 and not s.startswith('0'))
    print(f"\n全部 {len(all_syms)} 支 → 一般股票 {len(symbols)} 支（排除 ETF/權證）")
    
    # 設定計算日期範圍（最近一年）
    start_date = '2024-01-01'
    end_date = '2024-12-31'
    
    print(f"計算期間: {start_date} 至 {end_date}")
    print("\n開始計算...")
    
    # 使用 FactorLibrary 的批次計算功能
    stats = factor_lib.calculate_and_store(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        factor_types=['value', 'momentum', 'quality'],
        batch_size=100
    )
    
    print("\n" + "=" * 80)
    print("計算完成")
    print("=" * 80)
    print(f"處理: {stats['processed']:,} 筆")
    print(f"新增: {stats['inserted']:,} 筆")
    print(f"更新: {stats['updated']:,} 筆")
    print(f"失敗: {stats['failed']:,} 筆")
    if stats['processed'] > 0:
        print(f"成功率: {((stats['inserted'] + stats['updated']) / stats['processed'] * 100):.2f}%")
    print("=" * 80)

if __name__ == '__main__':
    recalculate_factors()
