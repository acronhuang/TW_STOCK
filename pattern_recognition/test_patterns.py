#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
形態學12神招 - 快速測試腳本
用於驗證系統功能和進行快速掃描測試

作者: 技術分析系統
日期: 2026-02-13
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pattern_recognition.patterns_12_masters import Pattern12Masters, format_signal_report
from pattern_recognition.market_scanner import MarketScanner, PatternScreener


def generate_test_data(pattern_type='w_bottom', days=120):
    """
    生成測試資料
    
    參數:
        pattern_type: 型態類型
        days: 天數
    """
    dates = pd.date_range(end=datetime.now(), periods=days)
    
    if pattern_type == 'w_bottom':
        # 生成W底型態
        prices = []
        base = 50
        
        # 下跌段
        for i in range(30):
            prices.append(base - i * 0.5)
        
        # 第一個底
        for i in range(10):
            prices.append(35 + np.random.random())
        
        # 反彈到頸線
        for i in range(15):
            prices.append(36 + i * 0.6)
        
        # 第二個底
        for i in range(10):
            prices.append(45 - i * 0.8)
        for i in range(10):
            prices.append(36 + np.random.random())
        
        # 突破
        for i in range(45):
            prices.append(45 + i * 0.3)
            
    elif pattern_type == 'm_top':
        # 生成M頭型態
        prices = []
        base = 30
        
        # 上漲到第一個頭
        for i in range(30):
            prices.append(base + i * 0.8)
        
        # 回落
        for i in range(20):
            prices.append(54 - i * 0.4)
        
        # 第二個頭
        for i in range(20):
            prices.append(46 + i * 0.4)
        
        # 跌破頸線
        for i in range(50):
            prices.append(54 - i * 0.5)
    
    else:
        # 隨機資料
        prices = np.random.random(days) * 10 + 50
    
    # 生成OHLCV
    data = []
    for i, date in enumerate(dates):
        close = prices[i] if i < len(prices) else 50
        high = close * (1 + np.random.random() * 0.02)
        low = close * (1 - np.random.random() * 0.02)
        open_price = (high + low) / 2
        volume = np.random.randint(1000000, 5000000)
        
        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    return pd.DataFrame(data)


def test_single_pattern():
    """測試單一型態檢測"""
    print("\n" + "="*80)
    print("測試 1: 單一型態檢測")
    print("="*80)
    
    detector = Pattern12Masters()
    
    # 測試W底
    print("\n測試 W底 型態...")
    df_w = generate_test_data('w_bottom')
    signal = detector._detect_w_bottom(df_w, 'TEST_W')
    
    if signal:
        print("✓ 成功檢測到 W底 型態")
        print(format_signal_report(signal))
    else:
        print("✗ 未檢測到 W底 型態")
    
    # 測試M頭
    print("\n測試 M頭 型態...")
    df_m = generate_test_data('m_top')
    signal = detector._detect_m_top(df_m, 'TEST_M')
    
    if signal:
        print("✓ 成功檢測到 M頭 型態")
        print(format_signal_report(signal))
    else:
        print("✗ 未檢測到 M頭 型態")


def test_market_scanner():
    """測試市場掃描器"""
    print("\n" + "="*80)
    print("測試 2: 市場掃描器")
    print("="*80)
    
    try:
        scanner = MarketScanner()
        
        # 測試取得股票列表
        symbols = scanner.get_all_stock_symbols()
        print(f"\n✓ 成功載入 {len(symbols)} 支股票")
        
        if symbols:
            # 測試掃描前3支股票
            test_symbols = symbols[:3]
            print(f"\n測試掃描: {', '.join(test_symbols)}")
            
            results = scanner.scan_market(
                symbols=test_symbols,
                min_confidence=0.70
            )
            
            print(f"\n✓ 掃描完成，找到 {len(results)} 個型態信號")
            
            if results:
                print("\n發現的型態:")
                for r in results[:5]:
                    print(f"  - {r['symbol']}: {r['pattern_name']} "
                          f"({r['signal_type']}, {r['confidence']*100:.0f}%)")
        else:
            print("\n⚠ 資料庫中沒有股票資料")
            
    except Exception as e:
        print(f"\n✗ 掃描器測試失敗: {e}")
        print("請確認MongoDB已啟動且包含必要資料")


def test_pattern_screener():
    """測試型態篩選器"""
    print("\n" + "="*80)
    print("測試 3: 型態篩選器")
    print("="*80)
    
    try:
        scanner = MarketScanner()
        symbols = scanner.get_all_stock_symbols()
        
        if not symbols:
            print("\n⚠ 資料庫中沒有股票資料，跳過此測試")
            return
        
        # 掃描市場
        test_symbols = symbols[:10]
        print(f"\n掃描 {len(test_symbols)} 支股票...")
        
        results = scanner.scan_market(
            symbols=test_symbols,
            min_confidence=0.70
        )
        
        if not results:
            print("\n⚠ 未找到任何型態信號")
            return
        
        # 測試篩選器
        screener = PatternScreener(scanner)
        
        # 測試高品質篩選
        high_quality = screener.screen_by_criteria(
            min_potential_gain=10.0,
            min_risk_reward=2.0
        )
        print(f"\n✓ 高品質信號: {len(high_quality)} 個")
        
        # 測試已確認型態
        confirmed = screener.get_confirmed_patterns_only()
        print(f"✓ 已確認型態: {len(confirmed)} 個")
        
        # 測試高信心度
        high_conf = screener.get_high_confidence_signals(0.80)
        print(f"✓ 高信心度信號: {len(high_conf)} 個")
        
        # 測試最佳風險報酬比
        best_rr = screener.get_best_risk_reward(5)
        print(f"✓ 最佳風險報酬比前5名:")
        for i, signal in enumerate(best_rr, 1):
            print(f"   {i}. {signal['symbol']}: {signal['pattern_name']} "
                  f"(報酬比 {signal['risk_reward']:.2f}:1)")
        
    except Exception as e:
        print(f"\n✗ 篩選器測試失敗: {e}")


def test_export_functions():
    """測試匯出功能"""
    print("\n" + "="*80)
    print("測試 4: 匯出功能")
    print("="*80)
    
    try:
        scanner = MarketScanner()
        symbols = scanner.get_all_stock_symbols()
        
        if not symbols:
            print("\n⚠ 資料庫中沒有股票資料，跳過此測試")
            return
        
        # 掃描少量股票
        test_symbols = symbols[:5]
        results = scanner.scan_market(symbols=test_symbols)
        
        if not results:
            print("\n⚠ 未找到任何型態信號")
            return
        
        # 測試文字報告
        print("\n測試文字報告生成...")
        report = scanner.generate_report('text')
        print("✓ 文字報告生成成功")
        print(report[:500] + "...")  # 顯示前500字
        
        # 測試JSON匯出
        print("\n測試JSON格式匯出...")
        json_report = scanner.generate_report('json')
        print(f"✓ JSON格式匯出成功 ({len(json_report)} 字元)")
        
        # 測試CSV匯出
        print("\n測試CSV檔案匯出...")
        test_file = 'test_pattern_scan.csv'
        scanner.export_to_csv(test_file)
        
        if os.path.exists(test_file):
            print(f"✓ CSV檔案匯出成功: {test_file}")
            # 清理測試檔案
            os.remove(test_file)
            print("✓ 測試檔案已清理")
        
    except Exception as e:
        print(f"\n✗ 匯出功能測試失敗: {e}")


def test_performance():
    """測試效能"""
    print("\n" + "="*80)
    print("測試 5: 效能測試")
    print("="*80)
    
    try:
        import time
        
        scanner = MarketScanner()
        symbols = scanner.get_all_stock_symbols()
        
        if not symbols:
            print("\n⚠ 資料庫中沒有股票資料，跳過此測試")
            return
        
        # 測試不同數量股票的掃描時間
        test_counts = [10, 20, 50] if len(symbols) >= 50 else [min(5, len(symbols))]
        
        for count in test_counts:
            test_symbols = symbols[:count]
            
            start_time = time.time()
            results = scanner.scan_market(symbols=test_symbols, max_workers=10)
            end_time = time.time()
            
            elapsed = end_time - start_time
            per_stock = elapsed / count if count > 0 else 0
            
            print(f"\n掃描 {count} 支股票:")
            print(f"  總時間: {elapsed:.2f} 秒")
            print(f"  平均每支: {per_stock:.2f} 秒")
            print(f"  找到信號: {len(results)} 個")
        
    except Exception as e:
        print(f"\n✗ 效能測試失敗: {e}")


def run_all_tests():
    """執行所有測試"""
    print("\n" + "="*80)
    print("形態學12神招 - 系統測試")
    print("="*80)
    print(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # 測試1: 單一型態檢測
    test_single_pattern()
    
    # 測試2: 市場掃描器
    test_market_scanner()
    
    # 測試3: 型態篩選器
    test_pattern_screener()
    
    # 測試4: 匯出功能
    test_export_functions()
    
    # 測試5: 效能測試
    test_performance()
    
    print("\n" + "="*80)
    print("所有測試完成")
    print("="*80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='形態學12神招 - 測試腳本')
    parser.add_argument('--test', choices=['all', 'pattern', 'scanner', 'screener', 'export', 'performance'],
                        default='all', help='選擇要執行的測試')
    
    args = parser.parse_args()
    
    if args.test == 'all':
        run_all_tests()
    elif args.test == 'pattern':
        test_single_pattern()
    elif args.test == 'scanner':
        test_market_scanner()
    elif args.test == 'screener':
        test_pattern_screener()
    elif args.test == 'export':
        test_export_functions()
    elif args.test == 'performance':
        test_performance()
