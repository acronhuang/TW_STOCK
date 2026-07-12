"""
移動平均線指標 (Moving Average)
支援簡單移動平均 (SMA) 和指數移動平均 (EMA)
"""

import pandas as pd
import numpy as np
from typing import Union, List


def calculate_ma(
    data: Union[pd.Series, pd.DataFrame],
    periods: Union[int, List[int]] = [5, 10, 20, 60, 120, 240],
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算簡單移動平均線 (Simple Moving Average, SMA)
    
    參數:
        data: 價格數據（Series 或 DataFrame）
        periods: 移動平均週期，可以是單一數字或列表（預設: [5, 10, 20, 60, 120, 240]）
        price_column: 價格欄位名稱（當 data 是 DataFrame 時使用，預設: 'close'）
    
    返回:
        DataFrame: 包含各週期移動平均線的資料
    
    範例:
        >>> import pandas as pd
        >>> df = pd.read_csv('stock_price.csv')
        >>> ma_df = calculate_ma(df, periods=[5, 10, 20])
        >>> print(ma_df.columns)
        Index(['MA_5', 'MA_10', 'MA_20'], dtype='object')
    """
    # 將單一週期轉換為列表
    if isinstance(periods, int):
        periods = [periods]
    
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算各週期移動平均
    result = pd.DataFrame(index=prices.index)
    
    for period in periods:
        ma_name = f'MA_{period}'
        result[ma_name] = prices.rolling(window=period, min_periods=period).mean()
    
    return result


def calculate_ema(
    data: Union[pd.Series, pd.DataFrame],
    periods: Union[int, List[int]] = [12, 26],
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算指數移動平均線 (Exponential Moving Average, EMA)
    
    EMA 對近期價格賦予更高權重，反應更靈敏
    
    參數:
        data: 價格數據（Series 或 DataFrame）
        periods: 移動平均週期（預設: [12, 26] for MACD）
        price_column: 價格欄位名稱（當 data 是 DataFrame 時使用）
    
    返回:
        DataFrame: 包含各週期指數移動平均線的資料
    
    範例:
        >>> ema_df = calculate_ema(df, periods=[12, 26])
        >>> print(ema_df.columns)
        Index(['EMA_12', 'EMA_26'], dtype='object')
    """
    # 將單一週期轉換為列表
    if isinstance(periods, int):
        periods = [periods]
    
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算各週期指數移動平均
    result = pd.DataFrame(index=prices.index)
    
    for period in periods:
        ema_name = f'EMA_{period}'
        result[ema_name] = prices.ewm(span=period, adjust=False).mean()
    
    return result


def calculate_ma_crossover(
    data: Union[pd.Series, pd.DataFrame],
    short_period: int = 5,
    long_period: int = 20,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算移動平均線交叉訊號
    
    黃金交叉 (Golden Cross): 短期均線上穿長期均線 → 買入訊號
    死亡交叉 (Death Cross): 短期均線下穿長期均線 → 賣出訊號
    
    參數:
        data: 價格數據
        short_period: 短期均線週期（預設: 5）
        long_period: 長期均線週期（預設: 20）
        price_column: 價格欄位名稱
    
    返回:
        DataFrame: 包含均線和交叉訊號
            - MA_short: 短期均線
            - MA_long: 長期均線
            - signal: 1=黃金交叉, -1=死亡交叉, 0=無訊號
    
    範例:
        >>> crossover = calculate_ma_crossover(df, short_period=5, long_period=20)
        >>> golden_cross = crossover[crossover['signal'] == 1]
        >>> death_cross = crossover[crossover['signal'] == -1]
    """
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算短期和長期均線
    result = pd.DataFrame(index=prices.index)
    result['MA_short'] = prices.rolling(window=short_period).mean()
    result['MA_long'] = prices.rolling(window=long_period).mean()
    
    # 計算均線差值
    result['ma_diff'] = result['MA_short'] - result['MA_long']
    result['ma_diff_prev'] = result['ma_diff'].shift(1)
    
    # 判斷交叉訊號
    # 黃金交叉: 前一日 diff < 0, 當日 diff > 0
    golden_cross = (result['ma_diff_prev'] < 0) & (result['ma_diff'] > 0)
    # 死亡交叉: 前一日 diff > 0, 當日 diff < 0
    death_cross = (result['ma_diff_prev'] > 0) & (result['ma_diff'] < 0)
    
    result['signal'] = 0
    result.loc[golden_cross, 'signal'] = 1   # 黃金交叉
    result.loc[death_cross, 'signal'] = -1   # 死亡交叉
    
    # 清理中間欄位
    result = result.drop(columns=['ma_diff', 'ma_diff_prev'])
    
    return result


def calculate_ma_support_resistance(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 60,
    price_column: str = 'close',
    tolerance: float = 0.02
) -> pd.DataFrame:
    """
    使用移動平均線識別支撐與壓力位
    
    當價格接近均線時（誤差容忍範圍內），視為測試支撐/壓力
    
    參數:
        data: 價格數據
        period: 均線週期（預設: 60日線，季線）
        price_column: 價格欄位名稱
        tolerance: 誤差容忍範圍（預設: 2%）
    
    返回:
        DataFrame: 包含均線和支撐/壓力測試標記
            - MA: 移動平均線
            - distance: 價格與均線的距離（百分比）
            - test_support: 是否測試支撐
            - test_resistance: 是否測試壓力
    """
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算均線
    result = pd.DataFrame(index=prices.index)
    result['MA'] = prices.rolling(window=period).mean()
    
    # 計算價格與均線的距離（百分比）
    result['distance'] = (prices - result['MA']) / result['MA']
    
    # 判斷是否測試支撐或壓力
    # 支撐: 價格略低於均線（-2% 到 0%）
    result['test_support'] = (result['distance'] >= -tolerance) & (result['distance'] < 0)
    
    # 壓力: 價格略高於均線（0% 到 +2%）
    result['test_resistance'] = (result['distance'] > 0) & (result['distance'] <= tolerance)
    
    return result


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    
    # 創建測試數據
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=100),
        'close': np.random.randn(100).cumsum() + 100
    })
    
    # 測試 SMA
    print("=" * 80)
    print("測試 SMA")
    print("=" * 80)
    ma = calculate_ma(test_data, periods=[5, 10, 20])
    print(ma.tail())
    
    # 測試 EMA
    print("\n" + "=" * 80)
    print("測試 EMA")
    print("=" * 80)
    ema = calculate_ema(test_data, periods=[12, 26])
    print(ema.tail())
    
    # 測試交叉訊號
    print("\n" + "=" * 80)
    print("測試均線交叉訊號")
    print("=" * 80)
    crossover = calculate_ma_crossover(test_data, short_period=5, long_period=20)
    signals = crossover[crossover['signal'] != 0]
    print(f"找到 {len(signals)} 個交叉訊號")
    print(signals)
    
    print("\n✅ 所有測試完成")
