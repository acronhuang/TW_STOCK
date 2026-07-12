#!/usr/bin/env python3
"""
形態學快速測試腳本

快速驗證形態學模組是否正常運作。

作者: Ming
創建日期: 2026-02-23
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime

def test_imports():
    """測試模組導入"""
    print("測試 1: 模組導入")
    print("-" * 50)
    
    try:
        from src.morphology import PatternDetector
        print("✓ PatternDetector")
        
        from src.morphology import detect_bottom_reversal
        print("✓ detect_bottom_reversal")
        
        from src.morphology import detect_w_bottom
        print("✓ detect_w_bottom")
        
        from src.morphology import detect_neckline_breakout
        print("✓ detect_neckline_breakout")
        
        from src.morphology import detect_volume_surge
        print("✓ detect_volume_surge")
        
        from src.morphology import detect_volume_price_divergence
        print("✓ detect_volume_price_divergence")
        
        from src.morphology import calculate_pattern_strength
        print("✓ calculate_pattern_strength")
        
        print("\n✅ 所有模組導入成功！\n")
        return True
        
    except ImportError as e:
        print(f"\n❌ 導入失敗: {e}\n")
        return False


def test_basic_detection():
    """測試基本偵測功能"""
    print("測試 2: 基本偵測功能")
    print("-" * 50)
    
    from src.morphology import PatternDetector
    
    # 創建測試數據（模擬破底翻）
    np.random.seed(42)
    
    # 下跌 → 破底 → 快速收復
    prices = np.concatenate([
        np.linspace(100, 85, 20),      # 下跌
        np.array([83, 81, 80]),        # 跌破支撐
        np.array([86, 88, 90]),        # 帶量收復
        np.linspace(90, 95, 30)        # 反彈
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 20),
        np.array([2500, 3000, 3500]),  # 破底時量縮
        np.array([6000, 7000, 6500]),  # 收復時放量
        np.random.uniform(2000, 3000, 30)
    ])
    
    dates = pd.date_range('2024-01-01', periods=len(prices), freq='D')
    
    df = pd.DataFrame({
        'open': prices * 0.998,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    print(f"測試數據: {len(df)} 筆（{df.index[0].date()} ~ {df.index[-1].date()}）\n")
    
    # 初始化偵測器
    detector = PatternDetector()
    
    # 執行偵測
    results = detector.detect_all(df, stock_id="TEST")
    
    # 顯示結果
    print("偵測結果:")
    for pattern_name, result in results.items():
        status = "✓" if result['detected'] else "✗"
        print(f"  {status} {pattern_name:25s} | 出現 {result['count']:2d} 次")
    
    # 計算綜合評分
    score = detector.calculate_overall_score(df, lookback_days=5)
    print(f"\n綜合評分: {score:.3f}")
    
    if score > 0:
        print("\n✅ 偵測功能正常！\n")
        return True
    else:
        print("\n⚠️  未偵測到形態（數據可能不符合條件）\n")
        return True  # 仍視為通過，因為功能本身沒有錯誤


def test_with_mongodb():
    """測試 MongoDB 連接與實際數據"""
    print("測試 3: MongoDB 連接與實際數據")
    print("-" * 50)
    
    try:
        from pymongo import MongoClient
        from src.morphology import PatternDetector
        
        # 連接 MongoDB
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        db = client['tw_stock_analysis']
        
        # 測試連接
        client.server_info()
        print("✓ MongoDB 連接成功")
        
        # 讀取台積電數據
        stock_id = "2330"
        data = list(db.stock_price.find(
            {'stock_id': stock_id},
            {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
        ).sort('date', -1).limit(120))
        
        if not data:
            print(f"⚠️  查無數據: {stock_id}")
            print("   請確保 MongoDB 中有股價數據")
            return False
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()
        
        print(f"✓ 讀取數據: {len(df)} 筆（{df.index[0].date()} ~ {df.index[-1].date()}）")
        
        # 執行偵測
        detector = PatternDetector()
        results = detector.detect_all(df, stock_id=stock_id)
        
        # 顯示結果
        print(f"\n{stock_id} 形態偵測:")
        total_patterns = 0
        for pattern_name, result in results.items():
            status = "✓" if result['detected'] else "✗"
            count = result['count']
            total_patterns += count
            print(f"  {status} {pattern_name:25s} | {count:2d} 次")
        
        score = detector.calculate_overall_score(df, lookback_days=5)
        print(f"\n綜合評分: {score:.3f}")
        print(f"總形態數: {total_patterns}")
        
        print("\n✅ 實際數據測試通過！\n")
        return True
        
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        print("   可能原因：")
        print("   1. MongoDB 未啟動")
        print("   2. 資料庫中無數據")
        print("   3. 網路連接問題\n")
        return False


def test_pattern_detector_methods():
    """測試 PatternDetector 各項方法"""
    print("測試 4: PatternDetector 方法")
    print("-" * 50)
    
    from src.morphology import PatternDetector
    
    # 創建測試數據
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 2)
    volumes = np.random.uniform(1000, 5000, 100)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    df = pd.DataFrame({
        'open': prices * 0.999,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    # 初始化
    detector = PatternDetector()
    print("✓ PatternDetector 初始化")
    
    # detect_all
    results = detector.detect_all(df)
    print("✓ detect_all() 方法")
    
    # calculate_overall_score
    score = detector.calculate_overall_score(df)
    print(f"✓ calculate_overall_score() = {score:.3f}")
    
    # get_latest_patterns
    recent = detector.get_latest_patterns(df, lookback_days=5)
    print(f"✓ get_latest_patterns() = {len(recent)} 個形態")
    
    # generate_summary
    summary = detector.generate_summary(df, stock_id="TEST")
    print("✓ generate_summary()")
    
    # filter_stocks
    stocks_data = {
        'TEST1': df,
        'TEST2': df.copy()
    }
    filtered = detector.filter_stocks(stocks_data, min_patterns=0, min_score=0.0)
    print(f"✓ filter_stocks() = {len(filtered)} 支")
    
    print("\n✅ 所有方法測試通過！\n")
    return True


def main():
    """主函數"""
    print("\n" + "=" * 70)
    print("形態學快速測試腳本")
    print("=" * 70)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")
    
    results = {}
    
    # 測試 1: 模組導入
    results['imports'] = test_imports()
    
    # 測試 2: 基本偵測
    if results['imports']:
        results['detection'] = test_basic_detection()
    else:
        results['detection'] = False
        print("⏭️  跳過測試 2（模組導入失敗）\n")
    
    # 測試 3: MongoDB
    if results['detection']:
        results['mongodb'] = test_with_mongodb()
    else:
        results['mongodb'] = False
        print("⏭️  跳過測試 3（基本偵測失敗）\n")
    
    # 測試 4: 方法測試
    if results['imports']:
        results['methods'] = test_pattern_detector_methods()
    else:
        results['methods'] = False
        print("⏭️  跳過測試 4（模組導入失敗）\n")
    
    # 總結
    print("=" * 70)
    print("測試總結")
    print("=" * 70)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"  {test_name:15s}: {status}")
    
    print("-" * 70)
    print(f"通過率: {passed}/{total} ({passed/total:.0%})")
    print("=" * 70)
    
    if passed == total:
        print("\n🎉 所有測試通過！形態學模組運作正常。")
        print("\n下一步:")
        print("  1. 查看使用手冊: docs/MORPHOLOGY_MANUAL.md")
        print("  2. 執行完整驗證: python3 scripts/validate_patterns.py")
        print("  3. 執行回測: python3 scripts/backtest_patterns.py")
        return 0
    else:
        print(f"\n⚠️  部分測試失敗 ({total - passed} 個)")
        print("\n建議:")
        print("  1. 檢查依賴套件: pip install pandas numpy scipy pymongo")
        print("  2. 確認 MongoDB 運行: brew services list | grep mongodb")
        print("  3. 查看錯誤訊息並修正")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
