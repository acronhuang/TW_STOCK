#!/usr/bin/env python3
"""
因子庫示例 - 計算和查詢因子

展示如何使用因子庫計算、存儲和查詢量化因子
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.factors import FactorLibrary

def main():
    print("="*80)
    print("因子庫示例 - 量化因子計算與查詢")
    print("="*80)
    print()
    
    # 建立因子庫
    factor_lib = FactorLibrary()
    
    # 示例 1: 計算並存儲因子
    print("【示例 1】計算並存儲因子")
    print("-" * 80)
    
    symbols = ['2330', '2317', '2454']  # 台積電、鴻海、聯發科
    start_date = '2024-01-01'
    end_date = '2024-12-31'
    
    print(f"股票: {', '.join(symbols)}")
    print(f"期間: {start_date} ~ {end_date}")
    print()
    
    # 計算所有因子類別
    print("計算因子中...")
    stats = factor_lib.calculate_and_store(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        factor_types=['value', 'momentum', 'quality'],
        batch_size=100
    )
    
    print()
    print(f"✅ 計算完成:")
    print(f"   處理: {stats['processed']} 筆")
    print(f"   新增: {stats['inserted']} 筆")
    print(f"   更新: {stats['updated']} 筆")
    print(f"   失敗: {stats['failed']} 筆")
    print()
    
    # 示例 2: 查詢單一股票的因子時間序列
    print("【示例 2】查詢台積電 (2330) 因子時間序列")
    print("-" * 80)
    
    factors_2330 = factor_lib.get_factors(
        symbol='2330',
        start_date='2024-01-01',
        end_date='2024-03-31'
    )
    
    print(f"資料筆數: {len(factors_2330)}")
    print()
    print("前 5 筆資料:")
    print(factors_2330.head())
    print()
    
    # 示例 3: 查詢橫斷面因子（某一天所有股票）
    print("【示例 3】查詢 2024-12-31 橫斷面因子")
    print("-" * 80)
    
    cross_section = factor_lib.get_cross_section(
        date='2024-12-31',
        factor_names=['pe_ratio', 'pb_ratio', 'roe', 'roa', 'return_1m']
    )
    
    print(f"股票數: {len(cross_section)}")
    print()
    print(cross_section)
    print()
    
    # 示例 4: 計算因子統計量
    print("【示例 4】計算 P/E Ratio 統計量")
    print("-" * 80)
    
    pe_stats = factor_lib.calculate_factor_stats(
        factor_name='pe_ratio',
        start_date='2024-01-01',
        end_date='2024-12-31'
    )
    
    if pe_stats:
        print(f"平均值: {pe_stats['mean']:.2f}")
        print(f"最小值: {pe_stats['min']:.2f}")
        print(f"最大值: {pe_stats['max']:.2f}")
        print(f"資料數: {pe_stats['count']}")
        print(f"覆蓋率: {pe_stats['coverage']:.2f}%")
    print()
    
    # 示例 5: 列出所有可用因子
    print("【示例 5】列出所有可用因子")
    print("-" * 80)
    
    available_factors = factor_lib.list_available_factors()
    
    print(f"共 {len(available_factors)} 個因子:")
    print()
    
    # 分類顯示
    value_factors = [f for f in available_factors if any(x in f for x in ['pe', 'pb', 'dividend', 'earnings'])]
    momentum_factors = [f for f in available_factors if any(x in f for x in ['return', 'rsi', 'volatility'])]
    quality_factors = [f for f in available_factors if any(x in f for x in ['roe', 'roa', 'margin', 'ratio'])]
    
    print("價值因子:")
    for f in value_factors:
        print(f"  - {f}")
    print()
    
    print("動能因子:")
    for f in momentum_factors:
        print(f"  - {f}")
    print()
    
    print("質量因子:")
    for f in quality_factors:
        print(f"  - {f}")
    print()
    
    # 匯出因子數據
    print("【匯出數據】")
    print("-" * 80)
    
    output_dir = project_root / "charts"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "factors_2330.csv"
    factors_2330.to_csv(output_file, index=False)
    print(f"✅ 台積電因子數據已匯出: {output_file}")
    
    print()
    print("="*80)
    print("因子庫示例完成！")
    print("="*80)

if __name__ == "__main__":
    main()
