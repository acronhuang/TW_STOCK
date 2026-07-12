"""
量價分析模組

包含兩個核心形態：
1. 量價噴出 (Volume Surge)
2. 量價背離 (Volume-Price Divergence)

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from typing import Tuple


def detect_volume_surge(
    df: pd.DataFrame,
    volume_ratio: float = 3.0,
    price_threshold: float = 1.05,
    lookback: int = 20
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    偵測量價噴出形態
    
    定義：成交量爆量且股價突破前高
    
    量化條件：
    1. volume > mean(volume, 5) * 3（成交量 3 倍以上）
    2. close > high(20)（突破 20 日高點）
    3. close > open * 1.05（當日漲幅 > 5%）
    
    Args:
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        volume_ratio: 成交量放大倍數（預設 3.0 倍）
        price_threshold: 當日漲幅閾值（預設 1.05，即 5%）
        lookback: 突破高點的回溯天數（預設 20 日）
    
    Returns:
        Tuple[pd.Series, pd.DataFrame]:
            - signal: Boolean Series，True 表示出現量價噴出
            - details: DataFrame，包含形態詳細資訊
    """
    # 輸入驗證
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")
    
    if len(df) < lookback:
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 計算 5 日平均成交量
    avg_volume_5 = df['volume'].rolling(5).mean()
    
    # 計算 20 日最高價
    high_20 = df['high'].rolling(lookback).max().shift(1)
    
    # 條件 1: 成交量爆量 3 倍
    cond1 = df['volume'] > avg_volume_5 * volume_ratio
    
    # 條件 2: 突破 20 日高點
    cond2 = df['close'] > high_20
    
    # 條件 3: 當日漲幅 > 5%
    cond3 = df['close'] > df['open'] * price_threshold
    
    # 綜合判斷
    signal = cond1 & cond2 & cond3
    
    # 計算詳細資訊
    details_list = []
    for idx in df[signal].index:
        i = df.index.get_loc(idx)
        
        # 計算形態強度評分
        volume_strength = min(df['volume'].iloc[i] / (avg_volume_5.iloc[i] * volume_ratio), 3.0) / 3.0
        price_strength = min((df['close'].iloc[i] - df['open'].iloc[i]) / df['open'].iloc[i] / 0.10, 1.0)
        breakout_strength = min((df['close'].iloc[i] - high_20.iloc[i]) / high_20.iloc[i] / 0.05, 1.0)
        
        pattern_score = (
            volume_strength * 0.4 +
            price_strength * 0.3 +
            breakout_strength * 0.3
        )
        
        details_list.append({
            'date': idx,
            'pattern': 'volume_surge',
            'open_price': df['open'].iloc[i],
            'close_price': df['close'].iloc[i],
            'intraday_gain': round((df['close'].iloc[i] - df['open'].iloc[i]) / df['open'].iloc[i], 4),
            'volume': df['volume'].iloc[i],
            'volume_ratio': round(df['volume'].iloc[i] / avg_volume_5.iloc[i], 2),
            'high_20': high_20.iloc[i],
            'pattern_score': round(pattern_score, 3)
        })
    
    # 轉換為 DataFrame
    details_df = pd.DataFrame(details_list)
    if not details_df.empty:
        details_df.set_index('date', inplace=True)
    
    return signal, details_df


def detect_volume_price_divergence(
    df: pd.DataFrame,
    window: int = 60,
    lookback_volume: int = 5,
    consecutive_days: int = 2
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    偵測量價背離形態（負背離，看跌訊號）
    
    定義：股價創新高但成交量未創新高
    
    量化條件：
    1. close == high(60)（股價創 60 日新高）
    2. volume < mean(volume, 5)（成交量低於 5 日均量）
    3. 連續 2 日出現此現象 → 出場訊號
    
    Args:
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        window: 新高回溯天數（預設 60 日）
        lookback_volume: 平均成交量計算天數（預設 5 日）
        consecutive_days: 連續出現天數閾值（預設 2 日）
    
    Returns:
        Tuple[pd.Series, pd.DataFrame]:
            - signal: Boolean Series，True 表示出現量價背離（看跌）
            - details: DataFrame，包含形態詳細資訊
    """
    # 輸入驗證
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")
    
    if len(df) < window:
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 計算 60 日最高價
    high_60 = df['high'].rolling(window).max()
    
    # 判斷是否創新高
    is_new_high = df['close'] >= high_60 * 0.999  # 容許 0.1% 誤差
    
    # 計算 5 日平均成交量
    avg_volume = df['volume'].rolling(lookback_volume).mean()
    
    # 成交量低於平均
    low_volume = df['volume'] < avg_volume
    
    # 單日背離
    single_divergence = is_new_high & low_volume
    
    # 連續 N 日出現背離
    signal = single_divergence.rolling(consecutive_days).sum() >= consecutive_days
    
    # 計算詳細資訊
    details_list = []
    for idx in df[signal].index:
        i = df.index.get_loc(idx)
        
        # 計算背離強度
        volume_decline = 1.0 - (df['volume'].iloc[i] / avg_volume.iloc[i])
        price_distance = (df['close'].iloc[i] - high_60.iloc[i]) / high_60.iloc[i]
        
        # 背離評分（越高越危險）
        divergence_score = min(volume_decline, 0.5) * 2.0  # 0-1
        
        details_list.append({
            'date': idx,
            'pattern': 'volume_price_divergence',
            'close_price': df['close'].iloc[i],
            'high_60': high_60.iloc[i],
            'volume': df['volume'].iloc[i],
            'avg_volume': avg_volume.iloc[i],
            'volume_ratio': round(df['volume'].iloc[i] / avg_volume.iloc[i], 2),
            'divergence_score': round(divergence_score, 3),
            'warning_level': 'HIGH' if divergence_score > 0.7 else 'MEDIUM'
        })
    
    # 轉換為 DataFrame
    details_df = pd.DataFrame(details_list)
    if not details_df.empty:
        details_df.set_index('date', inplace=True)
    
    return signal, details_df


def analyze_volume_trend(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    分析成交量趨勢（輔助判斷）
    
    Args:
        df: DataFrame
        window: 計算窗口
    
    Returns:
        pd.Series: 成交量趨勢評分（-1 到 1）
            > 0.5: 明顯放量趨勢
            -0.5 ~ 0.5: 溫和震盪
            < -0.5: 明顯縮量趨勢
    """
    # 計算成交量移動平均
    volume_ma = df['volume'].rolling(window).mean()
    
    # 計算趨勢（當前成交量與移動平均的偏離）
    trend = (df['volume'] - volume_ma) / volume_ma
    
    return trend


if __name__ == "__main__":
    # 測試範例
    print("量價分析模組測試")
    print("=" * 60)
    
    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)
    
    # 模擬量價噴出
    prices_surge = np.concatenate([
        np.linspace(100, 110, 40),  # 溫和上漲
        np.array([110, 116]),       # 突然爆量噴出
        np.linspace(116, 125, 30)
    ])
    
    volumes_surge = np.concatenate([
        np.random.uniform(1000, 2000, 40),
        np.array([8000, 9000]),     # 爆量
        np.random.uniform(2000, 3000, 30)
    ])
    
    df_surge = pd.DataFrame({
        'open': prices_surge * 0.995,
        'high': prices_surge * 1.01,
        'low': prices_surge * 0.99,
        'close': prices_surge,
        'volume': volumes_surge
    }, index=dates[:len(prices_surge)])
    
    # 測試量價噴出
    signal_surge, details_surge = detect_volume_surge(df_surge)
    print(f"\n【量價噴出】找到 {signal_surge.sum()} 個形態")
    if not details_surge.empty:
        print(details_surge.to_string())
    
    # 模擬量價背離
    prices_div = np.concatenate([
        np.linspace(100, 120, 60),  # 上漲
        np.linspace(120, 125, 10),  # 創新高但縮量
    ])
    
    volumes_div = np.concatenate([
        np.random.uniform(2000, 4000, 60),  # 正常量
        np.random.uniform(800, 1500, 10),   # 縮量
    ])
    
    df_div = pd.DataFrame({
        'open': prices_div * 0.998,
        'high': prices_div * 1.005,
        'low': prices_div * 0.995,
        'close': prices_div,
        'volume': volumes_div
    }, index=dates[:len(prices_div)])
    
    # 測試量價背離
    signal_div, details_div = detect_volume_price_divergence(df_div)
    print(f"\n【量價背離】找到 {signal_div.sum()} 個形態")
    if not details_div.empty:
        print(details_div.to_string())
