#!/usr/bin/env python3
"""
平行計算所有股票的因子數據

使用多進程加速因子計算，提升覆蓋率至 80%+

Usage:
    python3 scripts/parallel_factor_calculation.py --workers 4
    python3 scripts/parallel_factor_calculation.py --workers 8 --start-date 2024-01-01
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count
import time

# 添加 src 到路徑
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from factors import FactorLibrary
from pymongo import MongoClient


def calculate_factors_for_symbols(args):
    """
    為一組股票計算因子（worker 函數）
    
    Args:
        args: (symbols, start_date, end_date, worker_id)
    
    Returns:
        統計結果字典
    """
    symbols, start_date, end_date, worker_id = args
    
    print(f"[Worker {worker_id}] 開始處理 {len(symbols)} 支股票")
    
    # 每個 worker 建立自己的連接
    factor_lib = FactorLibrary()
    
    try:
        stats = factor_lib.calculate_and_store(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            factor_types=['value', 'momentum', 'quality', 'volume'],
            batch_size=100
        )
        
        print(f"[Worker {worker_id}] 完成: 處理 {stats['processed']:,} 筆, "
              f"新增 {stats['inserted']:,} 筆, 更新 {stats['updated']:,} 筆, "
              f"失敗 {stats['failed']:,} 筆")
        
        return stats
    
    except Exception as e:
        print(f"[Worker {worker_id}] 錯誤: {e}")
        return {'processed': 0, 'inserted': 0, 'updated': 0, 'failed': len(symbols)}


def split_list(lst, n):
    """將列表分割成 n 個大致相等的部分"""
    k, m = divmod(len(lst), n)
    return [lst[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n)]


def get_stock_symbols():
    """從資料庫獲取一般股票代碼（排除 ETF/權證/0開頭）"""
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    all_syms = db.stock_price.distinct('symbol')
    symbols = sorted(
        s for s in all_syms
        if s and s.isdigit() and len(s) == 4 and not s.startswith('0')
    )
    client.close()
    print(f"全部代碼 {len(all_syms)} 支 → 一般股票 {len(symbols)} 支（排除 ETF/權證）")
    return symbols


def check_current_coverage():
    """檢查當前因子覆蓋率"""
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 計算預期記錄數：應該基於實際有價格數據的記錄數
    # 而不是 股票數 × 交易日數（因為不是所有股票都在所有交易日有交易）
    price_records = db.stock_price.count_documents({})
    
    # 計算實際記錄數
    actual_total = db.stock_factors.count_documents({})
    
    # 按因子類別統計
    momentum_count = db.stock_factors.count_documents({'return_1m': {'$exists': True}})
    value_count = db.stock_factors.count_documents({'pe_ratio': {'$exists': True}})
    quality_count = db.stock_factors.count_documents({'roe': {'$exists': True}})
    
    client.close()
    
    # 基於實際價格記錄數計算覆蓋率
    coverage = (actual_total / price_records * 100) if price_records > 0 else 0
    momentum_coverage = (momentum_count / price_records * 100) if price_records > 0 else 0
    value_coverage = (value_count / price_records * 100) if price_records > 0 else 0
    quality_coverage = (quality_count / price_records * 100) if price_records > 0 else 0
    
    return {
        'price_records': price_records,
        'actual_total': actual_total,
        'coverage': coverage,
        'momentum_coverage': momentum_coverage,
        'value_coverage': value_coverage,
        'quality_coverage': quality_coverage
    }


def main():
    parser = argparse.ArgumentParser(description='平行計算股票因子數據')
    parser.add_argument('--workers', type=int, default=4,
                        help='並行 worker 數量 (預設: 4)')
    parser.add_argument('--start-date', type=str, default='2024-01-01',
                        help='開始日期 YYYY-MM-DD (預設: 2024-01-01)')
    parser.add_argument('--end-date', type=str, default=None,
                        help='結束日期 YYYY-MM-DD (預設: 昨天)')
    parser.add_argument('--symbols', type=str, nargs='+', default=None,
                        help='指定股票代碼列表 (預設: 全部)')
    
    args = parser.parse_args()
    
    # 設定結束日期為昨天（避免不完整數據）
    if args.end_date is None:
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        end_date = args.end_date
    
    print("=" * 80)
    print("平行計算股票因子數據")
    print("=" * 80)
    
    # 顯示當前覆蓋率
    print("\n📊 當前因子覆蓋率:")
    coverage = check_current_coverage()
    print(f"  價格記錄數: {coverage['price_records']:,}")
    print(f"  因子記錄數: {coverage['actual_total']:,}")
    print(f"  總覆蓋率:   {coverage['coverage']:.2f}%")
    print(f"  動能因子:   {coverage['momentum_coverage']:.2f}%")
    print(f"  價值因子:   {coverage['value_coverage']:.2f}%")
    print(f"  質量因子:   {coverage['quality_coverage']:.2f}%")
    
    # 獲取股票列表
    if args.symbols:
        symbols = args.symbols
        print(f"\n指定股票: {len(symbols)} 支")
    else:
        symbols = get_stock_symbols()
        print(f"\n全部股票: {len(symbols)} 支")
    
    print(f"日期範圍: {args.start_date} ~ {end_date}")
    print(f"Worker 數量: {args.workers}")
    print(f"CPU 核心數: {cpu_count()}")
    
    if args.workers > cpu_count():
        print(f"⚠️  警告: Worker 數量 ({args.workers}) 超過 CPU 核心數 ({cpu_count()})")
    
    # 將股票分組
    symbol_groups = split_list(symbols, args.workers)
    print(f"\n分組結果: {[len(g) for g in symbol_groups]}")
    
    # 準備參數
    worker_args = [
        (group, args.start_date, end_date, i+1)
        for i, group in enumerate(symbol_groups)
    ]
    
    # 開始計時
    start_time = time.time()
    print("\n" + "=" * 80)
    print("開始平行計算...")
    print("=" * 80 + "\n")
    
    # 使用多進程池
    with Pool(processes=args.workers) as pool:
        results = pool.map(calculate_factors_for_symbols, worker_args)
    
    # 統計總結果
    total_stats = {
        'processed': sum(r['processed'] for r in results),
        'inserted': sum(r['inserted'] for r in results),
        'updated': sum(r['updated'] for r in results),
        'failed': sum(r['failed'] for r in results)
    }
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("計算完成")
    print("=" * 80)
    print(f"總處理:   {total_stats['processed']:,} 筆")
    print(f"新增:     {total_stats['inserted']:,} 筆")
    print(f"更新:     {total_stats['updated']:,} 筆")
    print(f"失敗:     {total_stats['failed']:,} 筆")
    if total_stats['processed'] > 0:
        success_rate = ((total_stats['inserted'] + total_stats['updated']) / total_stats['processed'] * 100)
        print(f"成功率:   {success_rate:.2f}%")
    print(f"耗時:     {elapsed_time:.1f} 秒 ({elapsed_time/60:.1f} 分鐘)")
    
    # 顯示更新後覆蓋率
    print("\n📊 更新後因子覆蓋率:")
    coverage = check_current_coverage()
    print(f"  價格記錄數: {coverage['price_records']:,}")
    print(f"  因子記錄數: {coverage['actual_total']:,}")
    print(f"  總覆蓋率:   {coverage['coverage']:.2f}%")
    print(f"  動能因子:   {coverage['momentum_coverage']:.2f}%")
    print(f"  價值因子:   {coverage['value_coverage']:.2f}%")
    print(f"  質量因子:   {coverage['quality_coverage']:.2f}%")
    
    if coverage['coverage'] >= 80:
        print("\n✅ 成功! 因子覆蓋率已達 80%+ 目標")
    else:
        print(f"\n⚠️  當前覆蓋率 {coverage['coverage']:.2f}%，距離 80% 目標還需改善")
        print(f"   建議: 檢查價格數據和財報數據的完整性")
    
    print("=" * 80)


if __name__ == '__main__':
    main()
