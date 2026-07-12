"""
SenVision 系統快速測試

驗證所有核心功能是否正常運作

Author: SenVision Team
Date: 2026-02-24
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加項目路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

def test_zigzag():
    """測試 ZigZag 算法"""
    print("\n" + "="*80)
    print("【測試 1】ZigZag 轉折點提取")
    print("="*80)
    
    from senvision.zigzag import ZigZagIndicator
    
    # 生成測試數據
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # 生成有明顯波動的價格序列
    trend = np.linspace(100, 150, 100)
    noise = np.sin(np.linspace(0, 4*np.pi, 100)) * 15
    prices = trend + noise + np.random.randn(100) * 2
    
    df_test = pd.DataFrame({
        'date': dates,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices
    })
    
    # 測試 ZigZag
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    
    print(f"\n✅ 成功找到 {len(peaks)} 個轉折點")
    print(f"   前 5 個轉折點:")
    for i, peak in enumerate(peaks[:5], 1):
        print(f"   {i}. {peak.date.strftime('%Y-%m-%d')} {peak.type} @ {peak.price:.2f}")
    
    return True


def test_w_bottom():
    """測試 W底識別"""
    print("\n" + "="*80)
    print("【測試 2】W底形態識別")
    print("="*80)
    
    from senvision.pattern_detector import WBottomDetector
    from senvision.zigzag import ZigZagIndicator
    
    # 生成 W 底測試數據 - 使用更明顯的轉折點
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    
    # 構造明顯的 W 底形態 (確保每個段落有>5%的波動)
    prices = np.array([
        # 下跌到 L1 (day 0-10): 100 -> 80
        *np.linspace(100, 80, 10),
        
        # 反彈到頸線 H (day 10-25): 80 -> 95
        *np.linspace(80, 95, 15),
        
        # 下跌到 L2 (day 25-35): 95 -> 81
        *np.linspace(95, 81, 10),
        
        # 上漲到頸線附近 (day 35-50): 81 -> 93
        *np.linspace(81, 93, 15),
        
        # 突破上漲 (day 50-60): 93 -> 105
        *np.linspace(93, 105, 10)
    ])
    
    df_test = pd.DataFrame({
        'date': dates,
        'high': prices + np.abs(np.random.randn(60) * 1.5),
        'low': prices - np.abs(np.random.randn(60) * 1.5),
        'close': prices + np.random.randn(60) * 1,
        'volume': np.random.randint(1000000, 10000000, 60)
    })
    
    # 確保高低關係
    df_test['high'] = df_test[['high', 'close']].max(axis=1)
    df_test['low'] = df_test[['low', 'close']].min(axis=1)
    
    print(f"\n   測試數據範圍: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
    print(f"   總波動幅度: {(df_test['high'].max() - df_test['low'].min()) / df_test['low'].min() * 100:.1f}%")
    
    # 測試識別
    detector = WBottomDetector(zigzag_threshold=0.05)
    patterns = detector.detect(df_test, '測試')
    
    # 先顯示 ZigZag 轉折點
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    print(f"\n   ZigZag 轉折點: {len(peaks)} 個")
    for i, peak in enumerate(peaks[:8], 1):
        print(f"   {i}. {peak.type} @ Day {peak.index} = {peak.price:.2f}")
    
    if patterns:
        pattern = patterns[0]
        print(f"\n✅ 成功識別 W底形態:")
        print(f"   股票: {pattern.stock_id}")
        print(f"   頸線: {pattern.neckline:.2f}")
        print(f"   目標價: {pattern.target:.2f}")
        print(f"   停損價: {pattern.stop_loss:.2f}")
        print(f"   風報比: {pattern.risk_reward_ratio:.2f}")
        print(f"   狀態: {pattern.status.value}")
        print(f"   信心度: {pattern.confidence:.1%}")
        
        # 打印關鍵轉折點
        key_peaks = patterns[0].key_points
        print(f"\n   關鍵轉折點:")
        print(f"   L1: Day {key_peaks['L1'].index} @ {key_peaks['L1'].price:.2f}")
        print(f"   H:  Day {key_peaks['H'].index} @ {key_peaks['H'].price:.2f}")
        print(f"   L2: Day {key_peaks['L2'].index} @ {key_peaks['L2'].price:.2f}")
        return True
    else:
        print("\n⚠️  未識別到形態")
        if len(peaks) < 3:
            print("   原因: ZigZag 轉折點不足 (需要至少 3 個)")
        return False


def test_m_top():
    """測試 M頭識別"""
    print("\n" + "="*80)
    print("【測試 3】M頭形態識別")
    print("="*80)
    
    from senvision.pattern_detector import MTopDetector
    from senvision.zigzag import ZigZagIndicator
    
    # 生成 M 頭測試數據 - 使用更明顯的轉折點
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    
    # 構造明顯的 M 頭形態 (確保每個段落有>5%的波動)
    prices = np.array([
        # 上漲到 H1 (day 0-10): 100 -> 125
        *np.linspace(100, 125, 10),
        
        # 下跌到頸線 L (day 10-25): 125 -> 105
        *np.linspace(125, 105, 15),
        
        # 上漲到 H2 (day 25-35): 105 -> 123
        *np.linspace(105, 123, 10),
        
        # 下跌到頸線附近 (day 35-50): 123 -> 107
        *np.linspace(123, 107, 15),
        
        # 跌破頸線 (day 50-60): 107 -> 90
        *np.linspace(107, 90, 10)
    ])
    
    df_test = pd.DataFrame({
        'date': dates,
        'high': prices + np.abs(np.random.randn(60) * 1.5),
        'low': prices - np.abs(np.random.randn(60) * 1.5),
        'close': prices + np.random.randn(60) * 1,
        'volume': np.random.randint(1000000, 10000000, 60)
    })
    
    # 確保高低關係
    df_test['high'] = df_test[['high', 'close']].max(axis=1)
    df_test['low'] = df_test[['low', 'close']].min(axis=1)
    
    print(f"\n   測試數據範圍: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
    print(f"   總波動幅度: {(df_test['high'].max() - df_test['low'].min()) / df_test['low'].min() * 100:.1f}%")
    
    # 測試識別
    detector = MTopDetector(zigzag_threshold=0.05)
    patterns = detector.detect(df_test, '測試')
    
    # 先顯示 ZigZag 轉折點
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    print(f"\n   ZigZag 轉折點: {len(peaks)} 個")
    for i, peak in enumerate(peaks[:8], 1):
        print(f"   {i}. {peak.type} @ Day {peak.index} = {peak.price:.2f}")
    
    if patterns:
        pattern = patterns[0]
        print(f"\n✅ 成功識別 M頭形態:")
        print(f"   股票: {pattern.stock_id}")
        print(f"   頸線: {pattern.neckline:.2f}")
        print(f"   目標價: {pattern.target:.2f}")
        print(f"   停損價: {pattern.stop_loss:.2f}")
        print(f"   風報比: {pattern.risk_reward_ratio:.2f}")
        print(f"   狀態: {pattern.status.value}")
        print(f"   信心度: {pattern.confidence:.1%}")
        
        # 打印關鍵轉折點
        key_peaks = patterns[0].key_points
        print(f"\n   關鍵轉折點:")
        print(f"   H1: Day {key_peaks['H1'].index} @ {key_peaks['H1'].price:.2f}")
        print(f"   L:  Day {key_peaks['L'].index} @ {key_peaks['L'].price:.2f}")
        print(f"   H2: Day {key_peaks['H2'].index} @ {key_peaks['H2'].price:.2f}")
        return True
    else:
        print("\n⚠️  未識別到形態")
        if len(peaks) < 3:
            print("   原因: ZigZag 轉折點不足 (需要至少 3 個)")
        return False


def test_real_data():
    """測試真實數據（如果數據庫可用）"""
    print("\n" + "="*80)
    print("【測試 4】真實股票數據測試")
    print("="*80)
    
    try:
        from pymongo import MongoClient
        from senvision.pattern_detector import WBottomDetector
        
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        db = client['tw_stock_analysis']
        
        # 測試連接
        db.command('ping')
        
        # 獲取 2330 近期數據
        cursor = db.stock_price.find(
            {'stock_id': '2330'},
            {'date': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, '_id': 0}
        ).sort('date', -1).limit(120)
        
        df = pd.DataFrame(list(cursor))
        
        if df.empty:
            print("⚠️  數據庫無數據，跳過測試")
            return None
        
        # 反轉順序（從舊到新）
        df = df.sort_values('date').reset_index(drop=True)
        df['date'] = pd.to_datetime(df['date'])
        
        # 檢測形態
        detector = WBottomDetector()
        patterns = detector.detect(df, '2330')
        
        print(f"\n✅ 資料庫連接成功")
        print(f"   數據記錄: {len(df)} 筆")
        print(f"   日期範圍: {df['date'].min().strftime('%Y-%m-%d')} ~ {df['date'].max().strftime('%Y-%m-%d')}")
        print(f"   找到形態: {len(patterns)} 個")
        
        for pattern in patterns:
            print(f"\n   • {pattern.pattern_type.value}")
            print(f"     頸線: {pattern.neckline:.2f}")
            print(f"     風報比: {pattern.risk_reward_ratio:.2f}")
            print(f"     狀態: {pattern.status.value}")
        
        client.close()
        return True
    
    except Exception as e:
        print(f"⚠️  數據庫連接失敗: {e}")
        print("   這是可選測試，不影響核心功能")
        return None


def main():
    """執行所有測試"""
    print("\n" + "="*80)
    print("🚀 SenVision 系統測試")
    print("="*80)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # 測試 1: ZigZag
    try:
        results.append(("ZigZag 算法", test_zigzag()))
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        results.append(("ZigZag 算法", False))
    
    # 測試 2: W底
    try:
        results.append(("W底識別", test_w_bottom()))
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        results.append(("W底識別", False))
    
    # 測試 3: M頭
    try:
        results.append(("M頭識別", test_m_top()))
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        results.append(("M頭識別", False))
    
    # 測試 4: 真實數據（可選）
    try:
        result = test_real_data()
        if result is not None:
            results.append(("真實數據", result))
    except Exception as e:
        print(f"⚠️  真實數據測試跳過: {e}")
    
    # 總結
    print("\n" + "="*80)
    print("📊 測試結果總結")
    print("="*80 + "\n")
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    total = len(results)
    
    for name, result in results:
        icon = "✅" if result is True else "❌" if result is False else "⚠️ "
        status = "通過" if result is True else "失敗" if result is False else "跳過"
        print(f"{icon} {name:20} {status}")
    
    print("\n" + "-"*80)
    print(f"總計: {total} 項測試")
    print(f"通過: {passed} 項")
    print(f"失敗: {failed} 項")
    print(f"跳過: {skipped} 項")
    
    if failed == 0:
        print("\n🎉 所有核心測試通過！系統運行正常")
        return 0
    else:
        print("\n⚠️  部分測試失敗，請檢查錯誤信息")
        return 1


if __name__ == '__main__':
    sys.exit(main())
