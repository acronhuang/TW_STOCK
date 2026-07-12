"""
簡化測試 - 直接驗證 W底和M頭識別

使用手工構造的轉折點來確保測試有效
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加項目路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

def test_simple_w_bottom():
    """測試 W底識別 - 簡化版"""
    print("\n" + "="*80)
    print("【簡化測試】W底形態識別")
    print("="*80)
    
    from senvision.pattern_detector import WBottomDetector
    
    # 手工構造明確的 ZigZag 轉折點 - 需要確保回撤確認
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    
    # 創建帶明確轉折和回撤的 W 底形態
    prices = []
    
    # 段落 1: 初始 (Day 0-5)
    prices.extend([100.0] * 5)
    
    # 段落 2: 下跌到 L1 (Day 5-15) - 80
    for i in range(10):
        prices.append(100 - i * 2)  # 100 -> 80
    
    # 段落 3: 反彈到 H/頸線 (Day 15-28) - 96 (20% 上漲確認 L1)
    for i in range(13):
        prices.append(80 + i * 1.23)  # 80 -> 96
    
    # 段落 4: 下跌到 L2 (Day 28-40) - 82 (15% 下跌確認 H)
    for i in range(12):
        prices.append(96 - i * 1.17)  # 96 -> 82
    
    # 段落 5: 回到頸線附近 (Day 40-53) - 95 (16% 上漲確認 L2)
    for i in range(13):
        prices.append(82 + i)  # 82 -> 95
    
    # 段落 6: 突破 (Day 53-60) - 105
    for i in range(7):
        prices.append(95 + i * 1.4)  # 95 -> 105
    
    # 轉換為 numpy 數組並添加小波動
    np.random.seed(42)
    prices = np.array(prices)
    prices = prices + np.random.randn(len(prices)) * 0.3
    
    df_test = pd.DataFrame({
        'date': dates,
        'high': prices + np.abs(np.random.randn(len(prices)) * 0.5),
        'low': prices - np.abs(np.random.randn(len(prices)) * 0.5),
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, len(prices))
    })
    
    # 確保高低關係
    df_test['high'] = df_test[['high', 'close']].max(axis=1)
    df_test['low'] = df_test[['low', 'close']].min(axis=1)
    
    print(f"\n📊 測試數據:")
    print(f"   範圍: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
    print(f"   跨度: {len(df_test)} 天")
    print(f"   波動: {((df_test['high'].max() - df_test['low'].min()) / df_test['low'].min() * 100):.1f}%")
    
    # 測試 ZigZag
    from senvision.zigzag import ZigZagIndicator
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    
    print(f"\n🔍 ZigZag 轉折點: {len(peaks)} 個")
    for i, peak in enumerate(peaks, 1):
        print(f"   {i}. Day {peak.index:2d} | {peak.type} @ {peak.price:.2f}")
    
    # 測試識別
    print(f"\n🔎 W底識別:")
    detector = WBottomDetector(zigzag_threshold=0.05)
    patterns = detector.detect(df_test, 'TEST')
    
    if patterns:
        for i, pattern in enumerate(patterns, 1):
            print(f"\n✅ 識別到第 {i} 個 W底:")
            print(f"   頸線: {pattern.neckline:.2f}")
            print(f"   目標價: {pattern.target:.2f}")
            print(f"   停損價: {pattern.stop_loss:.2f}")
            print(f"   風報比: {pattern.risk_reward_ratio:.2f}")
            print(f"   狀態: {pattern.status.value}")
            print(f"   信心度: {pattern.confidence:.1%}")
            
            # 關鍵轉折點
            kp = pattern.key_points
            print(f"\n   轉折點:")
            print(f"   L1: Day {kp['L1'].index} @ {kp['L1'].price:.2f}")
            print(f"   H:  Day {kp['H'].index} @ {kp['H'].price:.2f}")
            print(f"   L2: Day {kp['L2'].index} @ {kp['L2'].price:.2f}")
        return True
    else:
        print("❌ 未識別到形態")
        if len(peaks) < 3:
            print(f"   原因: ZigZag 轉折點不足 ({len(peaks)} < 3)")
        else:
            print("   原因: 未找到符合條件的 L-H-L 序列")
        return False


def test_simple_m_top():
    """測試 M頭識別 - 簡化版"""
    print("\n" + "="*80)
    print("【簡化測試】M頭形態識別")
    print("="*80)
    
    from senvision.pattern_detector import MTopDetector
    
    # 手工構造明確的 ZigZag 轉折點
    dates = pd.date_range('2024-01-01', periods=60, freq='D')
    
    # 創建帶明確轉折和回撤的 M 頭形態
    prices = []
    
    # 段落 1: 初始 (Day 0-5)
    prices.extend([100.0] * 5)
    
    # 段落 2: 上漲到 H1 (Day 5-15) - 130
    for i in range(10):
        prices.append(100 + i * 3)  # 100 -> 130
    
    # 段落 3: 下跌到 L/頸線 (Day 15-28) - 104 (20% 下跌確認 H1)
    for i in range(13):
        prices.append(130 - i * 2)  # 130 -> 104
    
    # 段落 4: 上漲到 H2 (Day 28-40) - 128 (23% 上漲確認 L)
    for i in range(12):
        prices.append(104 + i * 2)  # 104 -> 128
    
    # 段落 5: 回到頸線附近 (Day 40-53) - 105 (18% 下跌確認 H2)
    for i in range(13):
        prices.append(128 - i * 1.77)  # 128 -> 105
    
    # 段落 6: 跌破 (Day 53-60) - 90
    for i in range(7):
        prices.append(105 - i * 2.1)  # 105 -> 90
    
    # 轉換為 numpy 數組並添加小波動
    np.random.seed(42)
    prices = np.array(prices)
    prices = prices + np.random.randn(len(prices)) * 0.3
    
    df_test = pd.DataFrame({
        'date': dates,
        'high': prices + np.abs(np.random.randn(len(prices)) * 0.5),
        'low': prices - np.abs(np.random.randn(len(prices)) * 0.5),
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, len(prices))
    })
    
    # 確保高低關係
    df_test['high'] = df_test[['high', 'close']].max(axis=1)
    df_test['low'] = df_test[['low', 'close']].min(axis=1)
    
    print(f"\n📊 測試數據:")
    print(f"   範圍: {df_test['low'].min():.2f} - {df_test['high'].max():.2f}")
    print(f"   跨度: {len(df_test)} 天")
    print(f"   波動: {((df_test['high'].max() - df_test['low'].min()) / df_test['low'].min() * 100):.1f}%")
    
    # 測試 ZigZag
    from senvision.zigzag import ZigZagIndicator
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    
    print(f"\n🔍 ZigZag 轉折點: {len(peaks)} 個")
    for i, peak in enumerate(peaks, 1):
        print(f"   {i}. Day {peak.index:2d} | {peak.type} @ {peak.price:.2f}")
    
    # 測試識別
    print(f"\n🔎 M頭識別:")
    detector = MTopDetector(zigzag_threshold=0.05)
    patterns = detector.detect(df_test, 'TEST')
    
    if patterns:
        for i, pattern in enumerate(patterns, 1):
            print(f"\n✅ 識別到第 {i} 個 M頭:")
            print(f"   頸線: {pattern.neckline:.2f}")
            print(f"   目標價: {pattern.target:.2f}")
            print(f"   停損價: {pattern.stop_loss:.2f}")
            print(f"   風報比: {pattern.risk_reward_ratio:.2f}")
            print(f"   狀態: {pattern.status.value}")
            print(f"   信心度: {pattern.confidence:.1%}")
            
            # 關鍵轉折點
            kp = pattern.key_points
            print(f"\n   轉折點:")
            print(f"   H1: Day {kp['H1'].index} @ {kp['H1'].price:.2f}")
            print(f"   L:  Day {kp['L'].index} @ {kp['L'].price:.2f}")
            print(f"   H2: Day {kp['H2'].index} @ {kp['H2'].price:.2f}")
        return True
    else:
        print("❌ 未識別到形態")
        if len(peaks) < 3:
            print(f"   原因: ZigZag 轉折點不足 ({len(peaks)} < 3)")
        else:
            print("   原因: 未找到符合條件的 H-L-H 序列")
        return False


def main():
    print("\n" + "="*80)
    print("🧪 SenVision 簡化測試")
    print("="*80)
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # 測試 1: W底
    try:
        results.append(("W底識別", test_simple_w_bottom()))
    except Exception as e:
        print(f"\n❌ 測試異常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("W底識別", False))
    
    # 測試 2: M頭
    try:
        results.append(("M頭識別", test_simple_m_top()))
    except Exception as e:
        print(f"\n❌ 測試異常: {e}")
        import traceback
        traceback.print_exc()
        results.append(("M頭識別", False))
    
    # 總結
    print("\n" + "="*80)
    print("📊 測試結果總結")
    print("="*80 + "\n")
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    
    for name, result in results:
        icon = "✅" if result else "❌"
        status = "通過" if result else "失敗"
        print(f"{icon} {name:20} {status}")
    
    print(f"\n總計: {len(results)} 項測試")
    print(f"通過: {passed} 項")
    print(f"失敗: {failed} 項")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
