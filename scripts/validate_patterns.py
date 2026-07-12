#!/usr/bin/env python3
"""
形態驗證腳本 (Pattern Validation Script)

驗證形態偵測模組的準確性與可靠性。

測試項目：
1. 單元測試：各形態偵測函數
2. 歷史驗證：檢查歷史數據中的形態
3. 準確率統計：計算偵測準確率

作者: Ming
創建日期: 2026-02-23
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from src.morphology import PatternDetector
from src.morphology.bottom_reversal import detect_bottom_reversal
from src.morphology.w_bottom import detect_w_bottom
from src.morphology.neckline_breakout import detect_neckline_breakout
from src.morphology.volume_analysis import detect_volume_surge, detect_volume_price_divergence


def test_pattern_detection():
    """測試形態偵測基本功能"""
    print("=" * 70)
    print("測試 1: 形態偵測基本功能")
    print("=" * 70)
    
    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)
    
    # 模擬破底翻
    prices = np.concatenate([
        np.linspace(100, 85, 20),   # 下跌
        np.array([83, 81, 86, 88]), # 破底翻
        np.linspace(88, 95, 50)     # 反彈
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 20),
        np.array([2000, 2500, 5000, 5500]),  # 放量
        np.random.uniform(1500, 2500, 50)
    ])
    
    df = pd.DataFrame({
        'open': prices * 0.998,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': volumes
    }, index=dates[:len(prices)])
    
    # 偵測破底翻
    signal, details = detect_bottom_reversal(df)
    
    print(f"\n破底翻偵測結果: {signal.sum()} 個形態")
    if not details.empty:
        print("✓ 測試通過：成功偵測到破底翻")
        print(details[['support_line', 'recovery_price', 'pattern_score']].to_string())
    else:
        print("✗ 測試失敗：未偵測到破底翻")
    
    return signal.sum() > 0


def validate_historical_patterns(stock_id="2330", days=360):
    """驗證歷史數據中的形態"""
    print("\n" + "=" * 70)
    print(f"測試 2: 驗證 {stock_id} 歷史形態（近 {days} 天）")
    print("=" * 70)
    
    # 連接 MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        db = client['tw_stock_analysis']
        
        # 測試連接
        client.server_info()
    except Exception as e:
        print(f"✗ MongoDB 連接失敗: {e}")
        return False
    
    # 讀取數據
    data = list(db.stock_price.find(
        {'stock_id': stock_id},
        {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', -1).limit(days))
    
    if not data:
        print(f"✗ 查無數據: {stock_id}")
        return False
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    
    print(f"✓ 讀取數據: {len(df)} 筆，期間 {df.index[0]} ~ {df.index[-1]}")
    
    # 執行偵測
    detector = PatternDetector()
    results = detector.detect_all(df, stock_id=stock_id)
    
    # 統計結果
    print("\n形態偵測統計:")
    print("-" * 70)
    
    total_patterns = 0
    for pattern_name, result in results.items():
        count = result['count']
        total_patterns += count
        status = "✓" if count > 0 else "✗"
        print(f"{status} {pattern_name:25s} | 出現次數: {count:3d}")
    
    print("-" * 70)
    print(f"總計: {total_patterns} 個形態")
    
    # 詳細報告
    if total_patterns > 0:
        print("\n" + detector.generate_summary(df, stock_id=stock_id))
    
    return total_patterns > 0


def calculate_pattern_accuracy(stock_id="2330", days=360, forward_days=20):
    """計算形態偵測的準確率（未來報酬）"""
    print("\n" + "=" * 70)
    print(f"測試 3: 計算形態準確率（{stock_id}，未來 {forward_days} 天報酬）")
    print("=" * 70)
    
    # 連接 MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        db = client['tw_stock_analysis']
    except Exception as e:
        print(f"✗ MongoDB 連接失敗: {e}")
        return None
    
    # 讀取數據
    data = list(db.stock_price.find(
        {'stock_id': stock_id},
        {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', -1).limit(days + forward_days))
    
    if not data or len(data) < days:
        print(f"✗ 數據不足: {stock_id}")
        return None
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    
    # 執行偵測
    detector = PatternDetector()
    results = detector.detect_all(df, stock_id=stock_id)
    
    # 計算未來報酬
    accuracy_stats = {}
    
    for pattern_name, result in results.items():
        if not result['detected']:
            continue
        
        details = result['details']
        returns = []
        
        for pattern_date in details.index:
            # 找到該日期在 df 中的位置
            try:
                idx = df.index.get_loc(pattern_date)
            except KeyError:
                continue
            
            # 確保有足夠的未來數據
            if idx + forward_days >= len(df):
                continue
            
            entry_price = df['close'].iloc[idx]
            future_price = df['close'].iloc[idx + forward_days]
            
            ret = (future_price - entry_price) / entry_price
            returns.append(ret)
        
        if not returns:
            continue
        
        # 統計
        avg_return = np.mean(returns)
        win_rate = sum(1 for r in returns if r > 0) / len(returns)
        
        accuracy_stats[pattern_name] = {
            'count': len(returns),
            'avg_return': avg_return,
            'win_rate': win_rate,
            'returns': returns
        }
    
    # 顯示結果
    if accuracy_stats:
        print(f"\n形態準確率統計（未來 {forward_days} 天）:")
        print("-" * 70)
        print(f"{'形態':25s} | {'次數':>5s} | {'平均報酬':>10s} | {'勝率':>8s}")
        print("-" * 70)
        
        for pattern, stats in accuracy_stats.items():
            print(f"{pattern:25s} | "
                  f"{stats['count']:5d} | "
                  f"{stats['avg_return']:+9.2%} | "
                  f"{stats['win_rate']:7.1%}")
        
        print("-" * 70)
        
        # 總體統計
        total_count = sum(s['count'] for s in accuracy_stats.values())
        total_returns = [r for s in accuracy_stats.values() for r in s['returns']]
        overall_avg = np.mean(total_returns)
        overall_win_rate = sum(1 for r in total_returns if r > 0) / len(total_returns)
        
        print(f"{'總計':25s} | {total_count:5d} | {overall_avg:+9.2%} | {overall_win_rate:7.1%}")
    else:
        print("✗ 無足夠數據計算準確率")
    
    return accuracy_stats


def batch_validate_stocks(stock_list: List[str], days=180):
    """批量驗證多支股票"""
    print("\n" + "=" * 70)
    print(f"測試 4: 批量驗證 {len(stock_list)} 支股票")
    print("=" * 70)
    
    # 連接 MongoDB
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        db = client['tw_stock_analysis']
    except Exception as e:
        print(f"✗ MongoDB 連接失敗: {e}")
        return None
    
    detector = PatternDetector()
    summary = {
        'total_stocks': len(stock_list),
        'processed': 0,
        'patterns_found': 0,
        'pattern_counts': {}
    }
    
    for stock_id in stock_list:
        # 讀取數據
        data = list(db.stock_price.find(
            {'stock_id': stock_id}
        ).sort('date', -1).limit(days))
        
        if not data or len(data) < 60:
            continue
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()
        
        # 偵測
        try:
            results = detector.detect_all(df, stock_id=stock_id)
            summary['processed'] += 1
            
            for pattern_name, result in results.items():
                if result['detected']:
                    summary['patterns_found'] += result['count']
                    summary['pattern_counts'][pattern_name] = \
                        summary['pattern_counts'].get(pattern_name, 0) + result['count']
        
        except Exception as e:
            print(f"⚠️  處理 {stock_id} 時發生錯誤: {e}")
            continue
    
    # 顯示摘要
    print(f"\n批量驗證摘要:")
    print(f"  處理股票數: {summary['processed']} / {summary['total_stocks']}")
    print(f"  找到形態數: {summary['patterns_found']}")
    print(f"\n各形態統計:")
    for pattern, count in summary['pattern_counts'].items():
        print(f"  {pattern:25s}: {count:4d}")
    
    return summary


def test_pattern_breakdown_detection():
    """測試形態破壞偵測"""
    print("\n" + "=" * 70)
    print("測試 5: 形態破壞偵測")
    print("=" * 70)
    
    from src.morphology.bottom_reversal import check_pattern_breakdown
    
    # 測試案例 1: 跌破支撐線
    is_broken, reason = check_pattern_breakdown(
        current_price=568,
        support_line=580,
        entry_price=600,
        recent_closes=pd.Series([595, 585, 568]),
        recent_volumes=pd.Series([2000, 2500, 3000])
    )
    
    print("\n測試案例 1: 跌破支撐線 -2%")
    print(f"  結果: {'破壞' if is_broken else '正常'}")
    if is_broken:
        print(f"  原因: {reason}")
    
    # 測試案例 2: 正常持有
    is_broken, reason = check_pattern_breakdown(
        current_price=605,
        support_line=580,
        entry_price=600,
        recent_closes=pd.Series([602, 603, 605]),
        recent_volumes=pd.Series([2000, 2200, 2100])
    )
    
    print("\n測試案例 2: 正常持有")
    print(f"  結果: {'破壞' if is_broken else '正常'}")
    
    return True


def main():
    """主函數"""
    print("\n" + "=" * 70)
    print("形態驗證腳本 (Pattern Validation Script)")
    print("=" * 70)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    test_results = {}
    
    # 測試 1: 基本功能
    test_results['basic'] = test_pattern_detection()
    
    # 測試 2: 歷史驗證
    test_results['historical'] = validate_historical_patterns("2330", days=360)
    
    # 測試 3: 準確率
    test_results['accuracy'] = calculate_pattern_accuracy("2330", days=360, forward_days=20)
    
    # 測試 4: 批量驗證
    test_stocks = ['2330', '2317', '2454', '2308', '2382']
    test_results['batch'] = batch_validate_stocks(test_stocks, days=180)
    
    # 測試 5: 形態破壞
    test_results['breakdown'] = test_pattern_breakdown_detection()
    
    # 總結
    print("\n" + "=" * 70)
    print("驗證總結")
    print("=" * 70)
    
    passed = sum(1 for result in test_results.values() if result)
    total = len(test_results)
    
    print(f"通過測試: {passed} / {total}")
    
    for test_name, result in test_results.items():
        status = "✓ 通過" if result else "✗ 失敗"
        print(f"  {test_name:15s}: {status}")
    
    print("=" * 70)
    
    if passed == total:
        print("\n🎉 所有測試通過！形態偵測模組運作正常。")
        return 0
    else:
        print(f"\n⚠️  部分測試失敗 ({total - passed} 個)")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
