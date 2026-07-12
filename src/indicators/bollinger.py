"""
布林通道 (Bollinger Bands)
衡量價格波動範圍和超買超賣
"""

import pandas as pd
import numpy as np
from typing import Union, Tuple


def calculate_bollinger_bands(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 20,
    std_dev: float = 2.0,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算布林通道
    
    布林通道由三條線組成:
    - 中軌 (Middle Band): N 日移動平均線
    - 上軌 (Upper Band): 中軌 + K 倍標準差
    - 下軌 (Lower Band): 中軌 - K 倍標準差
    
    交易訊號:
    - 價格觸及上軌: 超買，可能回調
    - 價格觸及下軌: 超賣，可能反彈
    - 價格突破上軌: 強勢突破
    - 價格跌破下軌: 弱勢跌破
    - 通道寬度收窄: 盤整，可能大行情
    - 通道寬度擴張: 波動加劇
    
    參數:
        data: 價格數據（Series 或 DataFrame）
        period: 移動平均週期（預設: 20）
        std_dev: 標準差倍數（預設: 2.0）
        price_column: 價格欄位名稱
    
    返回:
        DataFrame: 包含布林通道指標
            - BB_Middle: 中軌
            - BB_Upper: 上軌
            - BB_Lower: 下軌
            - BB_Width: 通道寬度百分比
            - BB_Percent: 價格在通道內的位置 (0-1)
    
    範例:
        >>> bb_df = calculate_bollinger_bands(df)
        >>> print(bb_df.tail())
    """
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算中軌（移動平均）
    middle_band = prices.rolling(window=period).mean()
    
    # 計算標準差
    rolling_std = prices.rolling(window=period).std()
    
    # 計算上軌和下軌
    upper_band = middle_band + (std_dev * rolling_std)
    lower_band = middle_band - (std_dev * rolling_std)
    
    # 計算通道寬度百分比
    bb_width = ((upper_band - lower_band) / middle_band) * 100
    
    # 計算價格在通道內的位置 (%B)
    # %B = 0: 價格在下軌
    # %B = 0.5: 價格在中軌
    # %B = 1: 價格在上軌
    bb_percent = (prices - lower_band) / (upper_band - lower_band)
    
    # 組合結果
    result = pd.DataFrame({
        'BB_Middle': middle_band,
        'BB_Upper': upper_band,
        'BB_Lower': lower_band,
        'BB_Width': bb_width,
        'BB_Percent': bb_percent
    }, index=prices.index)
    
    return result


def calculate_bollinger_signals(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 20,
    std_dev: float = 2.0,
    price_column: str = 'close',
    squeeze_threshold: float = 10.0
) -> pd.DataFrame:
    """
    計算布林通道交易訊號
    
    訊號規則:
    1. 價格突破上軌 → 強勢訊號
    2. 價格跌破下軌 → 弱勢訊號
    3. 價格從下軌反彈 → 買入訊號
    4. 價格從上軌回落 → 賣出訊號
    5. 通道收窄 (Squeeze) → 準備大行情
    
    參數:
        data: 價格數據
        period: 移動平均週期
        std_dev: 標準差倍數
        price_column: 價格欄位名稱
        squeeze_threshold: 通道擠壓門檻（預設: 10.0%）
    
    返回:
        DataFrame: 包含布林通道和交易訊號
            - BB_Middle, BB_Upper, BB_Lower: 布林通道
            - BB_Width, BB_Percent: 通道寬度和位置
            - signal: 1=買入, -1=賣出, 0=持有
            - position: above=上軌外, upper=中上部, middle=中部, lower=中下部, below=下軌外
            - squeeze: True=通道收窄, False=正常
    """
    # 提取價格
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算布林通道
    bb_df = calculate_bollinger_bands(data, period, std_dev, price_column)
    
    # 判斷價格位置
    bb_df['position'] = 'middle'
    bb_df.loc[prices > bb_df['BB_Upper'], 'position'] = 'above'
    bb_df.loc[prices < bb_df['BB_Lower'], 'position'] = 'below'
    bb_df.loc[(prices >= bb_df['BB_Middle']) & (prices <= bb_df['BB_Upper']), 'position'] = 'upper'
    bb_df.loc[(prices < bb_df['BB_Middle']) & (prices >= bb_df['BB_Lower']), 'position'] = 'lower'
    
    # 判斷通道擠壓
    bb_df['squeeze'] = bb_df['BB_Width'] < squeeze_threshold
    
    # 計算前一期的位置
    bb_df['position_prev'] = bb_df['position'].shift(1)
    
    # 生成交易訊號
    bb_df['signal'] = 0
    
    # 買入訊號: 價格從下軌外反彈進入通道
    buy_signal = (bb_df['position_prev'] == 'below') & (bb_df['position'].isin(['lower', 'middle']))
    bb_df.loc[buy_signal, 'signal'] = 1
    
    # 賣出訊號: 價格從上軌外回落進入通道
    sell_signal = (bb_df['position_prev'] == 'above') & (bb_df['position'].isin(['upper', 'middle']))
    bb_df.loc[sell_signal, 'signal'] = -1
    
    # 清理中間欄位
    bb_df = bb_df.drop(columns=['position_prev'])
    
    return bb_df


def calculate_bollinger_squeeze(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 20,
    std_dev: float = 2.0,
    price_column: str = 'close',
    lookback: int = 125
) -> pd.DataFrame:
    """
    檢測布林通道擠壓（Bollinger Squeeze）
    
    通道擠壓是指布林通道寬度收窄到極點，預示即將出現大行情。
    當 BB 寬度創下 N 日新低時，即為擠壓訊號。
    
    交易策略:
    - 擠壓期間: 等待突破方向
    - 擠壓後放大 + 突破上軌: 做多
    - 擠壓後放大 + 跌破下軌: 做空
    
    參數:
        data: 價格數據
        period: 移動平均週期
        std_dev: 標準差倍數
        price_column: 價格欄位名稱
        lookback: 判斷擠壓的回看週期（預設: 125 日）
    
    返回:
        DataFrame: 包含布林通道和擠壓訊號
            - BB_Middle, BB_Upper, BB_Lower: 布林通道
            - BB_Width: 通道寬度
            - squeeze_on: True=處於擠壓狀態
            - squeeze_off: True=擠壓解除（突破時機）
    """
    # 計算布林通道
    bb_df = calculate_bollinger_bands(data, period, std_dev, price_column)
    
    # 計算回看週期內的最小寬度
    bb_df['BB_Width_Min'] = bb_df['BB_Width'].rolling(window=lookback).min()
    
    # 判斷是否處於擠壓
    bb_df['squeeze_on'] = bb_df['BB_Width'] == bb_df['BB_Width_Min']
    
    # 判斷擠壓解除（前一期擠壓，當期不擠壓）
    bb_df['squeeze_on_prev'] = bb_df['squeeze_on'].shift(1)
    bb_df['squeeze_off'] = bb_df['squeeze_on_prev'] & (~bb_df['squeeze_on'])
    
    # 清理中間欄位
    bb_df = bb_df[['BB_Middle', 'BB_Upper', 'BB_Lower', 'BB_Width', 'squeeze_on', 'squeeze_off']]
    
    return bb_df


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    import numpy as np
    
    # 創建測試數據（模擬先盤整後突破）
    np.random.seed(42)
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=150),
        'close': np.concatenate([
            np.linspace(100, 105, 50) + np.random.randn(50) * 0.3,  # 盤整期
            np.linspace(105, 125, 50) + np.random.randn(50) * 2.0,  # 突破上漲
            np.linspace(125, 120, 50) + np.random.randn(50) * 1.5   # 回調
        ])
    })
    
    # 測試布林通道基本計算
    print("=" * 80)
    print("測試布林通道基本計算")
    print("=" * 80)
    bb_df = calculate_bollinger_bands(test_data)
    print(bb_df.tail(10))
    
    # 測試布林通道訊號
    print("\n" + "=" * 80)
    print("測試布林通道交易訊號")
    print("=" * 80)
    bb_signals = calculate_bollinger_signals(test_data)
    buy_signals = bb_signals[bb_signals['signal'] == 1]
    sell_signals = bb_signals[bb_signals['signal'] == -1]
    squeeze = bb_signals[bb_signals['squeeze'] == True]
    
    print(f"買入訊號數量: {len(buy_signals)}")
    print(f"賣出訊號數量: {len(sell_signals)}")
    print(f"通道擠壓數量: {len(squeeze)}")
    print("\n最近的訊號:")
    print(bb_signals[bb_signals['signal'] != 0].tail())
    
    # 測試布林通道擠壓
    print("\n" + "=" * 80)
    print("測試布林通道擠壓")
    print("=" * 80)
    squeeze_df = calculate_bollinger_squeeze(test_data, lookback=50)
    squeeze_on = squeeze_df[squeeze_df['squeeze_on'] == True]
    squeeze_off = squeeze_df[squeeze_df['squeeze_off'] == True]
    print(f"擠壓期間數量: {len(squeeze_on)}")
    print(f"擠壓解除數量: {len(squeeze_off)}")
    
    if len(squeeze_off) > 0:
        print("\n擠壓解除時機:")
        for idx, row in squeeze_off.iterrows():
            print(f"  日期: {test_data.loc[idx, 'date'].strftime('%Y-%m-%d')}, "
                  f"寬度: {row['BB_Width']:.2f}%")
    
    print("\n✅ 所有測試完成")
