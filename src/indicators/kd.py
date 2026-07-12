"""
KD 指標 (Stochastic Oscillator)
隨機指標，衡量價格動能和超買超賣
"""

import pandas as pd
import numpy as np
from typing import Union, Tuple


def calculate_kd(
    data: pd.DataFrame,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    high_column: str = 'high',
    low_column: str = 'low',
    close_column: str = 'close'
) -> pd.DataFrame:
    """
    計算 KD 指標
    
    KD 指標由兩條線組成:
    - K 值 (快線): 未成熟隨機值 (RSV) 的平滑移動平均
    - D 值 (慢線): K 值的移動平均
    
    計算公式:
    1. RSV = (收盤價 - N日最低價) / (N日最高價 - N日最低價) * 100
    2. K 值 = K 值前一日 * 2/3 + RSV * 1/3
    3. D 值 = D 值前一日 * 2/3 + K 值 * 1/3
    
    交易訊號:
    - K 值 > 80, D 值 > 80: 超買區，準備賣出
    - K 值 < 20, D 值 < 20: 超賣區，準備買入
    - K 線上穿 D 線: 黃金交叉，買入訊號
    - K 線下穿 D 線: 死亡交叉，賣出訊號
    
    參數:
        data: OHLC 數據
        k_period: K 值週期（預設: 9）
        d_period: D 值週期（預設: 3）
        slowing: 慢速平滑週期（預設: 3）
        high_column: 最高價欄位
        low_column: 最低價欄位
        close_column: 收盤價欄位
    
    返回:
        DataFrame: 包含 K 和 D 值
            - K: K 線（快線）
            - D: D 線（慢線）
            - RSV: 未成熟隨機值
    
    範例:
        >>> kd_df = calculate_kd(df)
        >>> print(kd_df.tail())
    """
    high = data[high_column]
    low = data[low_column]
    close = data[close_column]
    
    # 計算 N 日最高價和最低價
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    
    # 計算 RSV (未成熟隨機值)
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    
    # 對 RSV 進行平滑（if slowing > 1）
    if slowing > 1:
        rsv = rsv.rolling(window=slowing).mean()
    
    # 計算 K 值（使用 EMA 平滑）
    k = rsv.ewm(span=d_period * 2 - 1, adjust=False).mean()
    
    # 計算 D 值（K 值的平滑）
    d = k.ewm(span=d_period * 2 - 1, adjust=False).mean()
    
    # 組合結果
    result = pd.DataFrame({
        'K': k,
        'D': d,
        'RSV': rsv
    }, index=close.index)
    
    return result


def calculate_kd_signals(
    data: pd.DataFrame,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    overbought: float = 80,
    oversold: float = 20,
    high_column: str = 'high',
    low_column: str = 'low',
    close_column: str = 'close'
) -> pd.DataFrame:
    """
    計算 KD 交易訊號
    
    訊號規則:
    1. K 線上穿 D 線（黃金交叉）+ K < 80 → 買入訊號
    2. K 線下穿 D 線（死亡交叉）+ K > 20 → 賣出訊號
    3. K > 80 且 D > 80 → 超買警告
    4. K < 20 且 D < 20 → 超賣警告
    
    參數:
        data: OHLC 數據
        k_period: K 值週期
        d_period: D 值週期
        slowing: 慢速平滑週期
        overbought: 超買門檻（預設: 80）
        oversold: 超賣門檻（預設: 20）
        high_column: 最高價欄位
        low_column: 最低價欄位
        close_column: 收盤價欄位
    
    返回:
        DataFrame: 包含 KD 指標和交易訊號
            - K, D, RSV: KD 指標
            - signal: 1=買入, -1=賣出, 0=持有
            - zone: overbought=超買, oversold=超賣, neutral=中性
    """
    # 計算 KD
    kd_df = calculate_kd(data, k_period, d_period, slowing, high_column, low_column, close_column)
    
    # 判斷超買超賣區
    kd_df['zone'] = 'neutral'
    kd_df.loc[(kd_df['K'] > overbought) & (kd_df['D'] > overbought), 'zone'] = 'overbought'
    kd_df.loc[(kd_df['K'] < oversold) & (kd_df['D'] < oversold), 'zone'] = 'oversold'
    
    # 計算交叉訊號
    kd_df['k_above_d'] = kd_df['K'] > kd_df['D']
    kd_df['k_above_d_prev'] = kd_df['k_above_d'].shift(1)
    
    # 生成交易訊號
    kd_df['signal'] = 0
    
    # 黃金交叉: K 線上穿 D 線（且不在超買區）
    golden_cross = (~kd_df['k_above_d_prev']) & kd_df['k_above_d'] & (kd_df['K'] < overbought)
    kd_df.loc[golden_cross, 'signal'] = 1
    
    # 死亡交叉: K 線下穿 D 線（且不在超賣區）
    death_cross = kd_df['k_above_d_prev'] & (~kd_df['k_above_d']) & (kd_df['K'] > oversold)
    kd_df.loc[death_cross, 'signal'] = -1
    
    # 清理中間欄位
    kd_df = kd_df.drop(columns=['k_above_d', 'k_above_d_prev'])
    
    return kd_df


def calculate_kd_divergence(
    data: pd.DataFrame,
    k_period: int = 9,
    d_period: int = 3,
    slowing: int = 3,
    high_column: str = 'high',
    low_column: str = 'low',
    close_column: str = 'close',
    lookback: int = 20
) -> pd.DataFrame:
    """
    檢測 KD 背離
    
    背離是重要的反轉訊號:
    - 頂背離: 價格創新高，KD 未創新高 → 賣出訊號
    - 底背離: 價格創新低，KD 未創新低 → 買入訊號
    
    參數:
        data: OHLC 數據
        k_period: K 值週期
        d_period: D 值週期
        slowing: 慢速平滑週期
        high_column: 最高價欄位
        low_column: 最低價欄位
        close_column: 收盤價欄位
        lookback: 回看週期
    
    返回:
        DataFrame: 包含 KD 和背離訊號
            - K, D, RSV: KD 指標
            - divergence: bullish=買入, bearish=賣出, none=無
    """
    prices = data[close_column]
    
    # 計算 KD
    kd_df = calculate_kd(data, k_period, d_period, slowing, high_column, low_column, close_column)
    
    # 加入價格
    kd_df['price'] = prices
    
    # 計算回看週期內的最高/最低價和對應的 K 值
    kd_df['price_high'] = prices.rolling(window=lookback).max()
    kd_df['price_low'] = prices.rolling(window=lookback).min()
    kd_df['k_high'] = kd_df['K'].rolling(window=lookback).max()
    kd_df['k_low'] = kd_df['K'].rolling(window=lookback).min()
    
    # 判斷是否在高點/低點
    is_price_high = prices == kd_df['price_high']
    is_price_low = prices == kd_df['price_low']
    is_k_high = kd_df['K'] == kd_df['k_high']
    is_k_low = kd_df['K'] == kd_df['k_low']
    
    # 檢測背離
    kd_df['divergence'] = 'none'
    
    # 頂背離
    bearish_divergence = is_price_high & ~is_k_high
    kd_df.loc[bearish_divergence, 'divergence'] = 'bearish'
    
    # 底背離
    bullish_divergence = is_price_low & ~is_k_low
    kd_df.loc[bullish_divergence, 'divergence'] = 'bullish'
    
    # 清理中間欄位
    kd_df = kd_df[['K', 'D', 'RSV', 'divergence']]
    
    return kd_df


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    import numpy as np
    
    # 創建測試數據
    np.random.seed(42)
    n = 100
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n),
        'high': np.concatenate([
            np.linspace(100, 125, 50),
            np.linspace(125, 110, 50)
        ]) + np.random.randn(n) * 2,
        'low': np.concatenate([
            np.linspace(95, 120, 50),
            np.linspace(120, 105, 50)
        ]) + np.random.randn(n) * 2,
        'close': np.concatenate([
            np.linspace(98, 123, 50),
            np.linspace(123, 108, 50)
        ]) + np.random.randn(n) * 1.5
    })
    
    # 測試 KD 基本計算
    print("=" * 80)
    print("測試 KD 基本計算")
    print("=" * 80)
    kd_df = calculate_kd(test_data)
    print(kd_df.tail(10))
    
    # 測試 KD 訊號
    print("\n" + "=" * 80)
    print("測試 KD 交易訊號")
    print("=" * 80)
    kd_signals = calculate_kd_signals(test_data)
    buy_signals = kd_signals[kd_signals['signal'] == 1]
    sell_signals = kd_signals[kd_signals['signal'] == -1]
    overbought = kd_signals[kd_signals['zone'] == 'overbought']
    oversold = kd_signals[kd_signals['zone'] == 'oversold']
    
    print(f"買入訊號數量: {len(buy_signals)}")
    print(f"賣出訊號數量: {len(sell_signals)}")
    print(f"超買區數量: {len(overbought)}")
    print(f"超賣區數量: {len(oversold)}")
    print("\n最近的訊號:")
    print(kd_signals[kd_signals['signal'] != 0].tail())
    
    # 測試 KD 背離
    print("\n" + "=" * 80)
    print("測試 KD 背離")
    print("=" * 80)
    divergence = calculate_kd_divergence(test_data, lookback=20)
    bullish_div = divergence[divergence['divergence'] == 'bullish']
    bearish_div = divergence[divergence['divergence'] == 'bearish']
    print(f"底背離數量: {len(bullish_div)}")
    print(f"頂背離數量: {len(bearish_div)}")
    
    print("\n✅ 所有測試完成")
