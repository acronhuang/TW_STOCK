"""
MACD 指標 (Moving Average Convergence Divergence)
移動平均收斂發散指標，衡量趨勢強度和反轉時機
"""

import pandas as pd
import numpy as np
from typing import Union, Tuple


def calculate_macd(
    data: Union[pd.Series, pd.DataFrame],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算 MACD 指標
    
    MACD 由三個部分組成:
    1. MACD 線 (DIF): 快線 EMA - 慢線 EMA
    2. 訊號線 (DEM): MACD 線的 9 日 EMA
    3. 柱狀圖 (Histogram): MACD 線 - 訊號線
    
    交易訊號:
    - MACD 線上穿訊號線: 買入訊號（黃金交叉）
    - MACD 線下穿訊號線: 賣出訊號（死亡交叉）
    - 柱狀圖由負轉正: 趨勢轉強
    - 柱狀圖由正轉負: 趨勢轉弱
    
    參數:
        data: 價格數據（Series 或 DataFrame）
        fast_period: 快線 EMA 週期（預設: 12）
        slow_period: 慢線 EMA 週期（預設: 26）
        signal_period: 訊號線週期（預設: 9）
        price_column: 價格欄位名稱
    
    返回:
        DataFrame: 包含 MACD相關指標
            - MACD: MACD 線 (DIF)
            - Signal: 訊號線 (DEM)
            - Histogram: 柱狀圖
    
    範例:
        >>> macd_df = calculate_macd(df)
        >>> print(macd_df.columns)
        Index(['MACD', 'Signal', 'Histogram'], dtype='object')
    """
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算快線和慢線 EMA
    ema_fast = prices.ewm(span=fast_period, adjust=False).mean()
    ema_slow = prices.ewm(span=slow_period, adjust=False).mean()
    
    # 計算 MACD 線 (DIF)
    macd_line = ema_fast - ema_slow
    
    # 計算訊號線 (DEM)
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    
    # 計算柱狀圖 (Histogram)
    histogram = macd_line - signal_line
    
    # 組合結果
    result = pd.DataFrame({
        'MACD': macd_line,
        'Signal': signal_line,
        'Histogram': histogram
    }, index=prices.index)
    
    return result


def calculate_macd_signals(
    data: Union[pd.Series, pd.DataFrame],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算 MACD 交易訊號
    
    訊號規則:
    1. MACD 線上穿訊號線（黃金交叉）→ 買入訊號
    2. MACD 線下穿訊號線（死亡交叉）→ 賣出訊號
    3. 0 軸判斷: MACD > 0 多頭市場, MACD < 0 空頭市場
    
    參數:
        data: 價格數據
        fast_period: 快線 EMA 週期
        slow_period: 慢線 EMA 週期
        signal_period: 訊號線週期
        price_column: 價格欄位名稱
    
    返回:
        DataFrame: 包含 MACD 指標和交易訊號
            - MACD, Signal, Histogram: MACD 三件套
            - signal: 1=買入, -1=賣出, 0=持有
            - trend: bull=多頭, bear=空頭
    """
    # 計算 MACD
    macd_df = calculate_macd(data, fast_period, slow_period, signal_period, price_column)
    
    # 判斷趨勢
    macd_df['trend'] = 'bear'
    macd_df.loc[macd_df['MACD'] > 0, 'trend'] = 'bull'
    
    # 計算交叉訊號
    macd_df['macd_above_signal'] = macd_df['MACD'] > macd_df['Signal']
    macd_df['macd_above_signal_prev'] = macd_df['macd_above_signal'].shift(1)
    
    # 生成交易訊號
    macd_df['signal'] = 0
    
    # 黃金交叉: MACD 線上穿訊號線
    golden_cross = (~macd_df['macd_above_signal_prev']) & macd_df['macd_above_signal']
    macd_df.loc[golden_cross, 'signal'] = 1
    
    # 死亡交叉: MACD 線下穿訊號線
    death_cross = macd_df['macd_above_signal_prev'] & (~macd_df['macd_above_signal'])
    macd_df.loc[death_cross, 'signal'] = -1
    
    # 清理中間欄位
    macd_df = macd_df.drop(columns=['macd_above_signal', 'macd_above_signal_prev'])
    
    return macd_df


def calculate_macd_divergence(
    data: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_column: str = 'close',
    lookback: int = 20
) -> pd.DataFrame:
    """
    檢測 MACD 背離
    
    背離是重要的反轉訊號:
    - 頂背離: 價格創新高，MACD 未創新高 → 賣出訊號
    - 底背離: 價格創新低，MACD 未創新低 → 買入訊號
    
    參數:
        data: 包含價格的 DataFrame
        fast_period: 快線 EMA 週期
        slow_period: 慢線 EMA 週期
        signal_period: 訊號線週期
        price_column: 價格欄位名稱
        lookback: 回看週期
    
    返回:
        DataFrame: 包含 MACD 和背離訊號
            - MACD, Signal, Histogram: MACD 三件套
            - divergence: bullish=買入, bearish=賣出, none=無
    """
    prices = data[price_column]
    
    # 計算 MACD
    macd_df = calculate_macd(data, fast_period, slow_period, signal_period, price_column)
    
    # 加入價格
    macd_df['price'] = prices
    
    # 計算回看週期內的最高/最低價和對應的 MACD
    macd_df['price_high'] = prices.rolling(window=lookback).max()
    macd_df['price_low'] = prices.rolling(window=lookback).min()
    macd_df['macd_high'] = macd_df['MACD'].rolling(window=lookback).max()
    macd_df['macd_low'] = macd_df['MACD'].rolling(window=lookback).min()
    
    # 判斷是否在高點/低點
    is_price_high = prices == macd_df['price_high']
    is_price_low = prices == macd_df['price_low']
    is_macd_high = macd_df['MACD'] == macd_df['macd_high']
    is_macd_low = macd_df['MACD'] == macd_df['macd_low']
    
    # 檢測背離
    macd_df['divergence'] = 'none'
    
    # 頂背離
    bearish_divergence = is_price_high & ~is_macd_high
    macd_df.loc[bearish_divergence, 'divergence'] = 'bearish'
    
    # 底背離
    bullish_divergence = is_price_low & ~is_macd_low
    macd_df.loc[bullish_divergence, 'divergence'] = 'bullish'
    
    # 清理中間欄位
    macd_df = macd_df[['MACD', 'Signal', 'Histogram', 'divergence']]
    
    return macd_df


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    import numpy as np
    
    # 創建測試數據
    np.random.seed(42)
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=100),
        'close': np.concatenate([
            np.linspace(100, 120, 50),
            np.linspace(120, 105, 50)
        ]) + np.random.randn(100) * 0.5
    })
    
    # 測試 MACD 基本計算
    print("=" * 80)
    print("測試 MACD 基本計算")
    print("=" * 80)
    macd_df = calculate_macd(test_data)
    print(macd_df.tail(10))
    
    # 測試 MACD 訊號
    print("\n" + "=" * 80)
    print("測試 MACD 交易訊號")
    print("=" * 80)
    macd_signals = calculate_macd_signals(test_data)
    buy_signals = macd_signals[macd_signals['signal'] == 1]
    sell_signals = macd_signals[macd_signals['signal'] == -1]
    print(f"買入訊號數量: {len(buy_signals)}")
    print(f"賣出訊號數量: {len(sell_signals)}")
    print("\n最近的訊號:")
    print(macd_signals[macd_signals['signal'] != 0].tail())
    
    # 測試 MACD 背離
    print("\n" + "=" * 80)
    print("測試 MACD 背離")
    print("=" * 80)
    divergence = calculate_macd_divergence(test_data, lookback=20)
    bullish_div = divergence[divergence['divergence'] == 'bullish']
    bearish_div = divergence[divergence['divergence'] == 'bearish']
    print(f"底背離數量: {len(bullish_div)}")
    print(f"頂背離數量: {len(bearish_div)}")
    
    print("\n✅ 所有測試完成")
