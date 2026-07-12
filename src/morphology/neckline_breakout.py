"""
頸線突破 (Neckline Breakout) 形態偵測

定義：股價突破過去 60 日的高點連線（頸線），且振幅 > 3%。

量化條件：
1. close > neckline * 1.03（突破頸線 +3%）
2. (high - low) / close > 0.03（當日振幅 > 3%）
3. volume > mean(volume, 20) * 2.0（成交量爆量 2 倍）
4. 突破後連續 2 日站穩（避免假突破）

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


def detect_neckline_breakout(
    df: pd.DataFrame,
    window: int = 60,
    breakout_threshold: float = 1.03,
    amplitude_threshold: float = 0.03,
    volume_ratio: float = 2.0,
    confirmation_days: int = 2
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    偵測頸線突破形態
    
    Args:
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        window: 頸線計算週期（預設 60 日）
        breakout_threshold: 突破閾值（預設 1.03，即 +3%）
        amplitude_threshold: 振幅閾值（預設 0.03，即 3%）
        volume_ratio: 成交量放大倍數（預設 2.0 倍）
        confirmation_days: 確認天數（預設 2 日）
    
    Returns:
        Tuple[pd.Series, pd.DataFrame]:
            - signal: Boolean Series，True 表示出現頸線突破
            - details: DataFrame，包含形態詳細資訊
    """
    # 輸入驗證
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")
    
    if len(df) < window + confirmation_days:
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 計算頸線（60 日最高價的滾動最高）
    neckline = df['high'].rolling(window).max().shift(1)
    
    # 計算 20 日平均成交量
    avg_volume = df['volume'].rolling(20).mean()
    
    # 計算當日振幅
    amplitude = (df['high'] - df['low']) / df['close']
    
    # 初始化結果
    signal = pd.Series(False, index=df.index)
    details_list = []
    
    # 遍歷所有可能的突破點
    for i in range(window, len(df) - confirmation_days + 1):
        if pd.isna(neckline.iloc[i]) or pd.isna(avg_volume.iloc[i]):
            continue
        
        neck = neckline.iloc[i]
        
        # 條件 1: 突破頸線 +3%
        breakout = df['close'].iloc[i] > neck * breakout_threshold
        
        # 條件 2: 當日振幅 > 3%
        has_amplitude = amplitude.iloc[i] > amplitude_threshold
        
        # 條件 3: 成交量爆量 2 倍
        volume_surge = df['volume'].iloc[i] > avg_volume.iloc[i] * volume_ratio
        
        if not (breakout and has_amplitude and volume_surge):
            continue
        
        # 條件 4: 連續 2 日站穩
        confirmed = True
        for j in range(1, confirmation_days):
            if i + j >= len(df):
                confirmed = False
                break
            if df['close'].iloc[i + j] < neck:
                confirmed = False
                break
        
        if not confirmed:
            continue
        
        # 找到頸線突破形態
        signal.iloc[i] = True
        
        # 計算形態強度評分
        breakout_strength = min((df['close'].iloc[i] - neck) / neck / 0.05, 1.0)
        volume_strength = min(df['volume'].iloc[i] / (avg_volume.iloc[i] * volume_ratio), 2.0) / 2.0
        amplitude_strength = min(amplitude.iloc[i] / amplitude_threshold / 2.0, 1.0)
        
        pattern_score = (
            breakout_strength * 0.4 +
            volume_strength * 0.4 +
            amplitude_strength * 0.2
        )
        
        # 計算突破前的整理天數（頸線附近 ±5% 震盪）
        consolidation_days = 0
        for k in range(i - 1, max(0, i - 30), -1):
            if neck * 0.95 <= df['high'].iloc[k] <= neck * 1.05:
                consolidation_days += 1
            else:
                break
        
        details_list.append({
            'date': df.index[i],
            'pattern': 'neckline_breakout',
            'neckline': neck,
            'breakout_price': df['close'].iloc[i],
            'amplitude': round(amplitude.iloc[i], 4),
            'volume_ratio': round(df['volume'].iloc[i] / avg_volume.iloc[i], 2),
            'consolidation_days': consolidation_days,
            'pattern_score': round(pattern_score, 3)
        })
    
    # 轉換為 DataFrame
    details_df = pd.DataFrame(details_list)
    if not details_df.empty:
        details_df.set_index('date', inplace=True)
    
    return signal, details_df


def check_neckline_breakdown(
    current_price: float,
    neckline: float,
    entry_price: float
) -> Tuple[bool, str]:
    """
    檢查頸線突破形態是否破壞
    
    Args:
        current_price: 當前收盤價
        neckline: 頸線價格
        entry_price: 進場價格
    
    Returns:
        Tuple[bool, str]: (是否破壞, 破壞原因)
    """
    # 破壞條件 1: 跌破頸線 -3%
    if current_price < neckline * 0.97:
        return True, "跌破頸線 -3%"
    
    # 破壞條件 2: 從高點回落 -10%
    if (current_price - entry_price) / entry_price < -0.10:
        return True, "從進場價回落 -10%"
    
    return False, ""


def calculate_neckline_target(
    neckline: float,
    consolidation_low: float
) -> float:
    """
    計算頸線突破的理論目標價
    
    理論：突破後漲幅 = 整理區間高度
    
    Args:
        neckline: 頸線價格（整理區高點）
        consolidation_low: 整理區低點
    
    Returns:
        float: 理論目標價
    """
    height = neckline - consolidation_low
    target = neckline + height
    return target


def detect_false_breakout(
    df: pd.DataFrame,
    breakout_idx: int,
    neckline: float,
    lookback_days: int = 5
) -> bool:
    """
    偵測假突破（突破後快速跌回）
    
    Args:
        df: DataFrame
        breakout_idx: 突破日的索引
        neckline: 頸線價格
        lookback_days: 觀察天數
    
    Returns:
        bool: True 表示假突破
    """
    if breakout_idx + lookback_days >= len(df):
        return False
    
    future = df.iloc[breakout_idx:breakout_idx + lookback_days + 1]
    
    # 如果在 lookback_days 內收盤價跌破頸線，視為假突破
    false_breakout = (future['close'] < neckline).any()
    
    return false_breakout


if __name__ == "__main__":
    # 測試範例
    print("頸線突破形態偵測模組測試")
    print("=" * 60)
    
    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)
    
    # 模擬頸線突破：長期盤整後突破
    prices = np.concatenate([
        np.random.uniform(95, 105, 60),  # 60 天盤整（頸線約 105）
        np.array([106, 108, 110, 112, 115, 118]),  # 突破上漲
        np.linspace(118, 130, 20)  # 持續上漲
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 60),
        np.array([5000, 6000, 5500, 4500, 4000, 3500]),  # 突破時爆量
        np.random.uniform(2000, 3000, 20)
    ])
    
    df = pd.DataFrame({
        'open': prices * 0.995,
        'high': prices * 1.02,
        'low': prices * 0.98,
        'close': prices,
        'volume': volumes
    }, index=dates[:len(prices)])
    
    # 執行偵測
    signal, details = detect_neckline_breakout(df)
    
    print(f"\n找到 {signal.sum()} 個頸線突破形態")
    if not details.empty:
        print("\n形態詳細資訊：")
        print(details.to_string())
        
        # 計算理論目標價
        first_pattern = details.iloc[0]
        consolidation_low = df['low'].iloc[0:60].min()
        target = calculate_neckline_target(
            neckline=first_pattern['neckline'],
            consolidation_low=consolidation_low
        )
        print(f"\n整理區低點: {consolidation_low:.2f}")
        print(f"頸線: {first_pattern['neckline']:.2f}")
        print(f"理論目標價: {target:.2f}")
        print(f"突破價: {first_pattern['breakout_price']:.2f}")
        print(f"潛在漲幅: {(target - first_pattern['breakout_price']) / first_pattern['breakout_price'] * 100:.2f}%")
