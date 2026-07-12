"""
雙底 (W Bottom) 形態偵測

定義：形成兩個低點，第二底不破第一底，且突破頸線。

量化條件：
1. 偵測兩個局部低點（間隔 10-40 天）
2. low_2 >= low_1 * 0.98（第二底不破第一底 -2%）
3. close > neck_line * 1.03（突破頸線 +3%）
4. volume > mean(volume, 20) * 1.5（突破時放量）

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from typing import Tuple, List, Dict


def detect_w_bottom(
    df: pd.DataFrame,
    min_gap: int = 10,
    max_gap: int = 40,
    tolerance: float = 0.02,
    breakout_threshold: float = 1.03,
    volume_ratio: float = 1.5
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    偵測 W 底形態
    
    Args:
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        min_gap: 兩底最小間隔天數（預設 10 天）
        max_gap: 兩底最大間隔天數（預設 40 天）
        tolerance: 第二底容忍度（預設 0.02，即 -2%）
        breakout_threshold: 突破頸線閾值（預設 1.03，即 +3%）
        volume_ratio: 成交量放大倍數（預設 1.5 倍）
    
    Returns:
        Tuple[pd.Series, pd.DataFrame]:
            - signal: Boolean Series，True 表示出現 W 底
            - details: DataFrame，包含形態詳細資訊
    """
    # 輸入驗證
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")
    
    if len(df) < max_gap + 20:
        # 數據不足
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 找出局部低點（使用 scipy.signal）
    # order=5 表示前後 5 天都要比當天高，才算局部低點
    lows_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
    
    if len(lows_idx) < 2:
        # 沒有足夠的局部低點
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 初始化結果
    signal = pd.Series(False, index=df.index)
    details_list = []
    
    # 遍歷所有可能的雙底組合
    for i in range(len(lows_idx) - 1):
        idx1 = lows_idx[i]
        
        for j in range(i + 1, len(lows_idx)):
            idx2 = lows_idx[j]
            gap = idx2 - idx1
            
            # 檢查間隔是否在允許範圍內
            if gap < min_gap or gap > max_gap:
                continue
            
            low_1 = df['low'].iloc[idx1]
            low_2 = df['low'].iloc[idx2]
            
            # 條件 1: 第二底不破第一底（容忍 -2%）
            if low_2 < low_1 * (1 - tolerance):
                continue
            
            # 計算頸線（兩底之間的最高點）
            neck_line = df['high'].iloc[idx1:idx2+1].max()
            
            # 檢查後續是否突破頸線
            future_window = min(10, len(df) - idx2)
            future = df.iloc[idx2:idx2+future_window]
            
            # 計算 20 日平均成交量
            avg_volume = df['volume'].iloc[max(0, idx2-20):idx2].mean()
            
            for k in range(len(future)):
                actual_idx = idx2 + k
                
                # 條件 2: 突破頸線 +3%
                breakout = future['close'].iloc[k] > neck_line * breakout_threshold
                
                # 條件 3: 突破時放量
                volume_surge = future['volume'].iloc[k] > avg_volume * volume_ratio
                
                if breakout and volume_surge:
                    # 找到 W 底形態
                    signal.iloc[actual_idx] = True
                    
                    # 計算形態強度評分
                    bottom_symmetry = 1.0 - abs(low_2 - low_1) / low_1  # 對稱性
                    breakout_strength = min((future['close'].iloc[k] - neck_line) / neck_line / 0.05, 1.0)
                    volume_strength = min(future['volume'].iloc[k] / (avg_volume * volume_ratio), 2.0) / 2.0
                    
                    pattern_score = (
                        bottom_symmetry * 0.3 +
                        breakout_strength * 0.4 +
                        volume_strength * 0.3
                    )
                    
                    details_list.append({
                        'date': df.index[actual_idx],
                        'pattern': 'w_bottom',
                        'first_bottom_date': df.index[idx1],
                        'first_bottom_price': low_1,
                        'second_bottom_date': df.index[idx2],
                        'second_bottom_price': low_2,
                        'neckline': neck_line,
                        'breakout_price': future['close'].iloc[k],
                        'gap_days': gap,
                        'volume_ratio': future['volume'].iloc[k] / avg_volume,
                        'pattern_score': round(pattern_score, 3)
                    })
                    
                    break  # 找到後跳出
    
    # 轉換為 DataFrame
    details_df = pd.DataFrame(details_list)
    if not details_df.empty:
        details_df.set_index('date', inplace=True)
    
    return signal, details_df


def check_w_bottom_breakdown(
    current_price: float,
    neckline: float,
    second_bottom: float
) -> Tuple[bool, str]:
    """
    檢查 W 底形態是否破壞
    
    Args:
        current_price: 當前收盤價
        neckline: 頸線價格
        second_bottom: 第二底價格
    
    Returns:
        Tuple[bool, str]: (是否破壞, 破壞原因)
    """
    # 破壞條件 1: 跌破頸線 -3%
    if current_price < neckline * 0.97:
        return True, "跌破頸線 -3%"
    
    # 破壞條件 2: 創新低（跌破第二底）
    if current_price < second_bottom:
        return True, "創新低，跌破第二底"
    
    return False, ""


def calculate_w_bottom_target(
    neckline: float,
    second_bottom: float
) -> float:
    """
    計算 W 底的理論目標價
    
    理論：頸線突破後，理論漲幅 = 頸線 - 底部
    
    Args:
        neckline: 頸線價格
        second_bottom: 第二底價格
    
    Returns:
        float: 理論目標價
    """
    height = neckline - second_bottom
    target = neckline + height
    return target


if __name__ == "__main__":
    # 測試範例
    print("W 底形態偵測模組測試")
    print("=" * 60)
    
    # 創建測試數據（模擬 W 底）
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)
    
    # 模擬 W 底形態
    prices = np.concatenate([
        np.linspace(100, 85, 20),   # 下跌到第一底
        np.linspace(85, 95, 15),    # 反彈到頸線
        np.linspace(95, 86, 15),    # 回落到第二底
        np.linspace(86, 98, 10),    # 再次反彈到頸線
        np.linspace(98, 110, 20)    # 突破頸線上漲
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 20),
        np.random.uniform(1500, 2500, 15),
        np.random.uniform(1200, 2200, 15),
        np.random.uniform(2000, 3000, 10),
        np.random.uniform(4000, 6000, 20)  # 突破時大量
    ])
    
    df = pd.DataFrame({
        'open': prices * 1.005,
        'high': prices * 1.015,
        'low': prices * 0.985,
        'close': prices,
        'volume': volumes
    }, index=dates[:len(prices)])
    
    # 執行偵測
    signal, details = detect_w_bottom(df)
    
    print(f"\n找到 {signal.sum()} 個 W 底形態")
    if not details.empty:
        print("\n形態詳細資訊：")
        print(details.to_string())
        
        # 計算理論目標價
        first_pattern = details.iloc[0]
        target = calculate_w_bottom_target(
            neckline=first_pattern['neckline'],
            second_bottom=first_pattern['second_bottom_price']
        )
        print(f"\n理論目標價: {target:.2f}")
        print(f"突破價: {first_pattern['breakout_price']:.2f}")
        print(f"潛在漲幅: {(target - first_pattern['breakout_price']) / first_pattern['breakout_price'] * 100:.2f}%")
