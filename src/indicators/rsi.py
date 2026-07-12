"""
相對強弱指標 (RSI - Relative Strength Index)
衡量價格動能，判斷超買超賣狀態
"""

import pandas as pd
import numpy as np
from typing import Union


def calculate_rsi(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 14,
    price_column: str = 'close'
) -> pd.Series:
    """
    計算相對強弱指標 (RSI)
    
    RSI 範圍: 0-100
    - RSI > 70: 超買區，可能回調
    - RSI < 30: 超賣區，可能反彈
    - RSI = 50: 中性
    
    參數:
        data: 價格數據（Series 或 DataFrame）
        period: 計算週期（預設: 14）
        price_column: 價格欄位名稱（當 data 是 DataFrame 時使用）
    
    返回:
        Series: RSI 指標值
    
    範例:
        >>> rsi = calculate_rsi(df, period=14)
        >>> overbought = rsi[rsi > 70]  # 超買
        >>> oversold = rsi[rsi < 30]    # 超賣
    """
    # 提取價格序列
    if isinstance(data, pd.DataFrame):
        prices = data[price_column]
    else:
        prices = data
    
    # 計算價格變化
    delta = prices.diff()
    
    # 分離漲跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 計算平均漲幅和跌幅（使用 Wilder's smoothing）
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    # 計算 RS (Relative Strength)
    rs = avg_gain / avg_loss
    
    # 計算 RSI
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_rsi_signals(
    data: Union[pd.Series, pd.DataFrame],
    period: int = 14,
    overbought: float = 70,
    oversold: float = 30,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    計算 RSI 交易訊號
    
    訊號規則:
    1. RSI 進入超賣區（< 30）→ 潛在買入機會
    2. RSI 離開超賣區（> 30）→ 買入訊號
    3. RSI 進入超買區（> 70）→ 潛在賣出機會
    4. RSI 離開超買區（< 70）→ 賣出訊號
    
    參數:
        data: 價格數據
        period: RSI 計算週期
        overbought: 超買門檻（預設: 70）
        oversold: 超賣門檻（預設: 30）
        price_column: 價格欄位名稱
    
    返回:
        DataFrame: 包含 RSI 和交易訊號
            - RSI: RSI 指標值
            - signal: 1=買入, -1=賣出, 0=持有
            - status: overbought/oversold/neutral
    """
    # 計算 RSI
    rsi = calculate_rsi(data, period, price_column)
    
    # 建立結果 DataFrame
    result = pd.DataFrame(index=rsi.index)
    result['RSI'] = rsi
    
    # 判斷狀態
    result['status'] = 'neutral'
    result.loc[rsi > overbought, 'status'] = 'overbought'
    result.loc[rsi < oversold, 'status'] = 'oversold'
    
    # 計算狀態變化
    result['status_prev'] = result['status'].shift(1)
    
    # 生成交易訊號
    result['signal'] = 0
    
    # 買入訊號: RSI 從超賣區離開（從 < 30 變成 > 30）
    buy_signal = (result['status_prev'] == 'oversold') & (result['status'] != 'oversold')
    result.loc[buy_signal, 'signal'] = 1
    
    # 賣出訊號: RSI 從超買區離開（從 > 70 變成 < 70）
    sell_signal = (result['status_prev'] == 'overbought') & (result['status'] != 'overbought')
    result.loc[sell_signal, 'signal'] = -1
    
    # 清理中間欄位
    result = result.drop(columns=['status_prev'])
    
    return result


def calculate_rsi_divergence(
    data: pd.DataFrame,
    period: int = 14,
    price_column: str = 'close',
    lookback: int = 20
) -> pd.DataFrame:
    """
    檢測 RSI 背離（Divergence）
    
    背離是重要的反轉訊號:
    - 頂背離 (Bearish): 價格創新高，但 RSI 未創新高 → 賣出訊號
    - 底背離 (Bullish): 價格創新低，但 RSI 未創新低 → 買入訊號
    
    參數:
        data: 包含價格的 DataFrame
        period: RSI 計算週期
        price_column: 價格欄位名稱
        lookback: 回看週期，用於判斷新高/新低（預設: 20）
    
    返回:
        DataFrame: 包含 RSI 和背離訊號
            - RSI: RSI 指標值
            - divergence: bullish=買入, bearish=賣出, none=無
    """
    prices = data[price_column]
    
    # 計算 RSI
    rsi = calculate_rsi(data, period, price_column)
    
    # 建立結果
    result = pd.DataFrame(index=data.index)
    result['RSI'] = rsi
    result['price'] = prices
    
    # 計算回看週期內的最高/最低價和對應的 RSI
    result['price_high'] = prices.rolling(window=lookback).max()
    result['price_low'] = prices.rolling(window=lookback).min()
    result['rsi_high'] = rsi.rolling(window=lookback).max()
    result['rsi_low'] = rsi.rolling(window=lookback).min()
    
    # 判斷是否在高點/低點
    is_price_high = prices == result['price_high']
    is_price_low = prices == result['price_low']
    
    # 判斷 RSI 是否同步達到高點/低點
    is_rsi_high = rsi == result['rsi_high']
    is_rsi_low = rsi == result['rsi_low']
    
    # 檢測背離
    result['divergence'] = 'none'
    
    # 頂背離: 價格創新高但 RSI 未創新高
    bearish_divergence = is_price_high & ~is_rsi_high & (rsi < 70)
    result.loc[bearish_divergence, 'divergence'] = 'bearish'
    
    # 底背離: 價格創新低但 RSI 未創新低
    bullish_divergence = is_price_low & ~is_rsi_low & (rsi > 30)
    result.loc[bullish_divergence, 'divergence'] = 'bullish'
    
    # 清理中間欄位
    result = result[['RSI', 'divergence']]
    
    return result


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    import numpy as np
    
    # 創建測試數據（模擬股價從上漲到下跌的過程）
    np.random.seed(42)
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=100),
        'close': np.concatenate([
            np.linspace(100, 120, 50),  # 上漲
            np.linspace(120, 105, 50)   # 下跌
        ]) + np.random.randn(100) * 0.5
    })
    
    # 測試 RSI 基本計算
    print("=" * 80)
    print("測試 RSI 基本計算")
    print("=" * 80)
    rsi = calculate_rsi(test_data, period=14)
    print(f"RSI 平均值: {rsi.mean():.2f}")
    print(f"RSI 最大值: {rsi.max():.2f}")
    print(f"RSI 最小值: {rsi.min():.2f}")
    print("\n最後 5 筆 RSI:")
    print(rsi.tail())
    
    # 測試 RSI 訊號
    print("\n" + "=" * 80)
    print("測試 RSI 交易訊號")
    print("=" * 80)
    rsi_signals = calculate_rsi_signals(test_data, period=14)
    buy_signals = rsi_signals[rsi_signals['signal'] == 1]
    sell_signals = rsi_signals[rsi_signals['signal'] == -1]
    print(f"買入訊號數量: {len(buy_signals)}")
    print(f"賣出訊號數量: {len(sell_signals)}")
    
    # 測試 RSI 背離
    print("\n" + "=" * 80)
    print("測試 RSI 背離")
    print("=" * 80)
    divergence = calculate_rsi_divergence(test_data, period=14, lookback=20)
    bullish_div = divergence[divergence['divergence'] == 'bullish']
    bearish_div = divergence[divergence['divergence'] == 'bearish']
    print(f"底背離數量: {len(bullish_div)}")
    print(f"頂背離數量: {len(bearish_div)}")
    
    print("\n✅ 所有測試完成")
