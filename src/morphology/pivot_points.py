"""
轉折點識別模組 (Pivot Points Detection)

識別價格的局部高點和低點，作為支撐/壓力線和趨勢線的基礎。

算法：
- scipy.signal.argrelextrema - 識別局部極值
- 過濾顯著的轉折點

作者: Ming
創建日期: 2026-02-24
"""

import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from typing import Tuple, Optional


def detect_pivot_highs(
    df: pd.DataFrame,
    order: int = 5,
    method: str = 'argrelextrema'
) -> pd.Series:
    """
    識別局部高點（轉折高點）

    Args:
        df: DataFrame，必須包含 high 欄位
        order: 左右各需要比較的K線數量（預設5）
        method: 識別方法 ('argrelextrema' 或 'zigzag'，目前僅支持 argrelextrema)

    Returns:
        pd.Series: Boolean Series，True 表示該位置是轉折高點

    Example:
        >>> df = pd.read_csv('2330.csv')
        >>> pivot_highs = detect_pivot_highs(df, order=5)
        >>> print(f"找到 {pivot_highs.sum()} 個轉折高點")
    """
    # 輸入驗證
    if 'high' not in df.columns:
        raise ValueError("DataFrame 必須包含 'high' 欄位")

    if len(df) < order * 2 + 1:
        # 數據不足
        return pd.Series(False, index=df.index)

    # 使用 scipy.signal.argrelextrema 識別局部最大值
    # order=5 表示前後各5根K線都要比當前K線低，才算局部高點
    highs_idx = argrelextrema(df['high'].values, np.greater, order=order)[0]

    # 建立 Boolean Series
    signal = pd.Series(False, index=df.index)
    signal.iloc[highs_idx] = True

    return signal


def detect_pivot_lows(
    df: pd.DataFrame,
    order: int = 5,
    method: str = 'argrelextrema'
) -> pd.Series:
    """
    識別局部低點（轉折低點）

    Args:
        df: DataFrame，必須包含 low 欄位
        order: 左右各需要比較的K線數量（預設5）
        method: 識別方法 ('argrelextrema' 或 'zigzag'，目前僅支持 argrelextrema)

    Returns:
        pd.Series: Boolean Series，True 表示該位置是轉折低點

    Example:
        >>> df = pd.read_csv('2330.csv')
        >>> pivot_lows = detect_pivot_lows(df, order=5)
        >>> print(f"找到 {pivot_lows.sum()} 個轉折低點")
    """
    # 輸入驗證
    if 'low' not in df.columns:
        raise ValueError("DataFrame 必須包含 'low' 欄位")

    if len(df) < order * 2 + 1:
        # 數據不足
        return pd.Series(False, index=df.index)

    # 使用 scipy.signal.argrelextrema 識別局部最小值
    # order=5 表示前後各5根K線都要比當前K線高，才算局部低點
    lows_idx = argrelextrema(df['low'].values, np.less, order=order)[0]

    # 建立 Boolean Series
    signal = pd.Series(False, index=df.index)
    signal.iloc[lows_idx] = True

    return signal


def get_pivot_points(
    df: pd.DataFrame,
    order: int = 5,
    method: str = 'argrelextrema'
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    獲取所有轉折點的詳細資訊

    Args:
        df: DataFrame，必須包含 date (或索引), high, low 欄位
        order: 轉折點判斷參數（預設5）
        method: 識別方法（預設 'argrelextrema'）

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]:
            - pivot_highs_df: 包含日期、價格、索引的高點DataFrame
            - pivot_lows_df: 包含日期、價格、索引的低點DataFrame

    Example:
        >>> df = pd.read_csv('2330.csv', index_col='date', parse_dates=True)
        >>> pivot_highs, pivot_lows = get_pivot_points(df, order=5)
        >>> print(f"高點數: {len(pivot_highs)}, 低點數: {len(pivot_lows)}")
        >>> print(pivot_highs.head())
    """
    # 輸入驗證
    required_cols = ['high', 'low']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")

    # 識別轉折高點
    highs_signal = detect_pivot_highs(df, order=order, method=method)
    highs_idx = df.index[highs_signal]

    if len(highs_idx) > 0:
        pivot_highs_df = pd.DataFrame({
            'date': highs_idx,
            'price': df.loc[highs_idx, 'high'].values,
            'index': np.arange(len(df))[highs_signal.values]
        })
        pivot_highs_df.set_index('date', inplace=True)
    else:
        pivot_highs_df = pd.DataFrame(columns=['date', 'price', 'index'])
        if len(df) > 0:
            # 保持索引類型一致
            pivot_highs_df.index = pd.Index([], name='date', dtype=df.index.dtype)

    # 識別轉折低點
    lows_signal = detect_pivot_lows(df, order=order, method=method)
    lows_idx = df.index[lows_signal]

    if len(lows_idx) > 0:
        pivot_lows_df = pd.DataFrame({
            'date': lows_idx,
            'price': df.loc[lows_idx, 'low'].values,
            'index': np.arange(len(df))[lows_signal.values]
        })
        pivot_lows_df.set_index('date', inplace=True)
    else:
        pivot_lows_df = pd.DataFrame(columns=['date', 'price', 'index'])
        if len(df) > 0:
            # 保持索引類型一致
            pivot_lows_df.index = pd.Index([], name='date', dtype=df.index.dtype)

    return pivot_highs_df, pivot_lows_df


def filter_pivot_by_threshold(
    pivot_df: pd.DataFrame,
    threshold: float = 0.02
) -> pd.DataFrame:
    """
    過濾小幅度的轉折點，只保留顯著的價格變動

    Args:
        pivot_df: 轉折點 DataFrame（來自 get_pivot_points）
        threshold: 最小價格變動幅度（預設 2%）

    Returns:
        pd.DataFrame: 過濾後的轉折點

    Example:
        >>> pivot_highs, pivot_lows = get_pivot_points(df)
        >>> significant_highs = filter_pivot_by_threshold(pivot_highs, threshold=0.03)
        >>> print(f"顯著高點數: {len(significant_highs)}")
    """
    if len(pivot_df) == 0:
        return pivot_df

    filtered_pivots = []

    for i in range(len(pivot_df)):
        if i == 0:
            # 第一個轉折點總是保留
            filtered_pivots.append(i)
            continue

        current_price = pivot_df.iloc[i]['price']
        prev_price = pivot_df.iloc[filtered_pivots[-1]]['price']

        # 計算價格變動幅度
        price_change = abs(current_price - prev_price) / prev_price

        if price_change >= threshold:
            filtered_pivots.append(i)

    return pivot_df.iloc[filtered_pivots].copy()


def detect_zigzag(
    df: pd.DataFrame,
    threshold: float = 0.05
) -> pd.DataFrame:
    """
    ZigZag 算法識別重要轉折點

    ZigZag 算法過濾微小波動，只保留大於閾值的價格變動。

    Args:
        df: DataFrame，必須包含 high, low, close 欄位
        threshold: 價格變動閾值（預設5%）

    Returns:
        pd.DataFrame: 包含 date, price, direction('H'/'L') 的轉折點

    Example:
        >>> df = pd.read_csv('2330.csv', index_col='date', parse_dates=True)
        >>> zigzag_points = detect_zigzag(df, threshold=0.05)
        >>> print(zigzag_points)
    """
    # 輸入驗證
    required_cols = ['high', 'low', 'close']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")

    if len(df) < 2:
        return pd.DataFrame(columns=['date', 'price', 'direction'])

    zigzag_points = []

    # 初始化
    highs = df['high'].values
    lows = df['low'].values
    dates = df.index

    # 尋找第一個轉折點
    max_high = highs[0]
    max_high_idx = 0
    min_low = lows[0]
    min_low_idx = 0

    last_peak_type = None  # 'H' 或 'L'

    for i in range(1, len(df)):
        # 追蹤區間最高/最低
        if highs[i] > max_high:
            max_high = highs[i]
            max_high_idx = i
        if lows[i] < min_low:
            min_low = lows[i]
            min_low_idx = i

        # 判斷是否形成有效轉折
        if last_peak_type is None or last_peak_type == 'L':
            # 從高點回落判斷
            high_to_low = (max_high - lows[i]) / max_high
            if high_to_low >= threshold:
                # 形成下跌，最高點是波峰
                if last_peak_type != 'H':
                    zigzag_points.append({
                        'date': dates[max_high_idx],
                        'price': max_high,
                        'direction': 'H',
                        'index': max_high_idx
                    })
                last_peak_type = 'H'
                min_low = lows[i]
                min_low_idx = i

        if last_peak_type == 'H':
            # 從低點反彈判斷
            low_to_high = (highs[i] - min_low) / min_low
            if low_to_high >= threshold:
                # 形成上漲，最低點是波谷
                zigzag_points.append({
                    'date': dates[min_low_idx],
                    'price': min_low,
                    'direction': 'L',
                    'index': min_low_idx
                })
                last_peak_type = 'L'
                max_high = highs[i]
                max_high_idx = i

    # 轉換為 DataFrame
    if len(zigzag_points) == 0:
        zigzag_df = pd.DataFrame(columns=['price', 'direction', 'index'])
        zigzag_df.index.name = 'date'
    else:
        zigzag_df = pd.DataFrame(zigzag_points)
        zigzag_df.set_index('date', inplace=True)

    return zigzag_df


if __name__ == "__main__":
    # 測試範例
    print("轉折點識別模組測試")
    print("=" * 60)

    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)

    # 模擬複雜走勢（包含多個轉折點）
    prices = np.concatenate([
        np.linspace(100, 120, 30),   # 上漲
        np.linspace(120, 95, 25),    # 下跌
        np.linspace(95, 110, 20),    # 反彈
        np.linspace(110, 90, 30),    # 下跌
        np.linspace(90, 115, 25),    # 上漲
        np.linspace(115, 130, 20)    # 持續上漲
    ])

    # 添加隨機噪聲
    noise = np.random.normal(0, 2, len(prices))
    prices = prices + noise

    df = pd.DataFrame({
        'open': prices * 0.998,
        'high': prices * 1.015,
        'low': prices * 0.985,
        'close': prices,
        'volume': np.random.uniform(1000, 3000, len(prices))
    }, index=dates[:len(prices)])

    # 測試1：識別轉折高點
    print("\n測試1：識別轉折高點")
    pivot_highs_signal = detect_pivot_highs(df, order=5)
    print(f"找到 {pivot_highs_signal.sum()} 個轉折高點")

    # 測試2：識別轉折低點
    print("\n測試2：識別轉折低點")
    pivot_lows_signal = detect_pivot_lows(df, order=5)
    print(f"找到 {pivot_lows_signal.sum()} 個轉折低點")

    # 測試3：獲取轉折點詳細資訊
    print("\n測試3：獲取轉折點詳細資訊")
    pivot_highs, pivot_lows = get_pivot_points(df, order=5)
    print(f"\n轉折高點 DataFrame:")
    print(pivot_highs.head())
    print(f"\n轉折低點 DataFrame:")
    print(pivot_lows.head())

    # 測試4：過濾小幅度轉折點
    print("\n測試4：過濾小幅度轉折點")
    significant_highs = filter_pivot_by_threshold(pivot_highs, threshold=0.03)
    significant_lows = filter_pivot_by_threshold(pivot_lows, threshold=0.03)
    print(f"顯著高點數: {len(significant_highs)} (原始: {len(pivot_highs)})")
    print(f"顯著低點數: {len(significant_lows)} (原始: {len(pivot_lows)})")

    # 測試5：ZigZag 算法
    print("\n測試5：ZigZag 算法")
    zigzag_points = detect_zigzag(df, threshold=0.05)
    print(f"ZigZag 轉折點數: {len(zigzag_points)}")
    print(zigzag_points.head(10))

    print("\n✅ 所有測試完成")
