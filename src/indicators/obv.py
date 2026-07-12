"""
OBV 指標 (On-Balance Volume)
能量潮指標，衡量成交量與價格的關係
"""

import pandas as pd
import numpy as np
from typing import Union


def calculate_obv(
    data: pd.DataFrame,
    close_column: str = 'close',
    volume_column: str = 'trading_volume'
) -> pd.Series:
    """
    計算 OBV (On-Balance Volume) 能量潮指標
    
    OBV 透過累積成交量來衡量資金流向:
    - 價格上漲日: OBV += 當日成交量
    - 價格下跌日: OBV -= 當日成交量
    - 價格持平: OBV 不變
    
    應用:
    - OBV 上升: 資金流入，多頭力量強
    - OBV 下降: 資金流出，空頭力量強
    - 價量背離: 價格創新高而 OBV 未創新高，賣出訊號
    
    參數:
        data: 包含價格和成交量的 DataFrame
        close_column: 收盤價欄位
        volume_column: 成交量欄位
    
    返回:
        Series: OBV 指標值
    
    範例:
        >>> obv = calculate_obv(df)
        >>> print(obv.tail())
    """
    close = data[close_column]
    volume = data[volume_column]
    
    # 計算價格變動方向
    price_change = close.diff()
    
    # 根據價格方向決定成交量的正負
    signed_volume = pd.Series(0, index=volume.index, dtype='float64')
    signed_volume[price_change > 0] = volume[price_change > 0]
    signed_volume[price_change < 0] = -volume[price_change < 0]
    
    # 累積成交量
    obv = signed_volume.cumsum()
    
    return obv


def calculate_obv_signals(
    data: pd.DataFrame,
    ma_period: int = 20,
    close_column: str = 'close',
    volume_column: str = 'trading_volume'
) -> pd.DataFrame:
    """
    計算 OBV 交易訊號
    
    訊號規則:
    1. OBV 上穿均線: 買入訊號
    2. OBV 下穿均線: 賣出訊號
    3. OBV 創新高 + 價格創新高: 確認多頭
    4. OBV 創新低 + 價格創新低: 確認空頭
    
    參數:
        data: 包含價格和成交量的 DataFrame
        ma_period: OBV 均線週期（預設: 20）
        close_column: 收盤價欄位
        volume_column: 成交量欄位
    
    返回:
        DataFrame: 包含 OBV 指標和交易訊號
            - OBV: OBV 指標值
            - OBV_MA: OBV 移動平均線
            - signal: 1=買入, -1=賣出, 0=持有
            - trend: bullish=多頭, bearish=空頭
    """
    # 計算 OBV
    obv = calculate_obv(data, close_column, volume_column)
    
    # 計算 OBV 移動平均線
    obv_ma = obv.rolling(window=ma_period).mean()
    
    # 判斷趨勢
    result = pd.DataFrame({
        'OBV': obv,
        'OBV_MA': obv_ma
    }, index=data.index)
    
    result['trend'] = 'bearish'
    result.loc[result['OBV'] > result['OBV_MA'], 'trend'] = 'bullish'
    
    # 計算交叉訊號
    result['obv_above_ma'] = result['OBV'] > result['OBV_MA']
    result['obv_above_ma_prev'] = result['obv_above_ma'].shift(1)
    
    # 生成交易訊號
    result['signal'] = 0
    
    # 黃金交叉: OBV 上穿均線
    golden_cross = (~result['obv_above_ma_prev']) & result['obv_above_ma']
    result.loc[golden_cross, 'signal'] = 1
    
    # 死亡交叉: OBV 下穿均線
    death_cross = result['obv_above_ma_prev'] & (~result['obv_above_ma'])
    result.loc[death_cross, 'signal'] = -1
    
    # 清理中間欄位
    result = result.drop(columns=['obv_above_ma', 'obv_above_ma_prev'])
    
    return result


def calculate_obv_divergence(
    data: pd.DataFrame,
    close_column: str = 'close',
    volume_column: str = 'trading_volume',
    lookback: int = 20
) -> pd.DataFrame:
    """
    檢測 OBV 背離
    
    背離是重要的反轉訊號:
    - 頂背離: 價格創新高，OBV 未創新高 → 賣出訊號（量能不支持上漲）
    - 底背離: 價格創新低，OBV 未創新低 → 買入訊號（量能不支持下跌）
    
    參數:
        data: 包含價格和成交量的 DataFrame
        close_column: 收盤價欄位
        volume_column: 成交量欄位
        lookback: 回看週期
    
    返回:
        DataFrame: 包含 OBV 和背離訊號
            - OBV: OBV 指標值
            - divergence: bullish=買入, bearish=賣出, none=無
    """
    prices = data[close_column]
    
    # 計算 OBV
    obv = calculate_obv(data, close_column, volume_column)
    
    # 組合結果
    result = pd.DataFrame({
        'OBV': obv,
        'price': prices
    }, index=data.index)
    
    # 計算回看週期內的最高/最低價和對應的 OBV
    result['price_high'] = prices.rolling(window=lookback).max()
    result['price_low'] = prices.rolling(window=lookback).min()
    result['obv_high'] = obv.rolling(window=lookback).max()
    result['obv_low'] = obv.rolling(window=lookback).min()
    
    # 判斷是否在高點/低點
    is_price_high = prices == result['price_high']
    is_price_low = prices == result['price_low']
    is_obv_high = obv == result['obv_high']
    is_obv_low = obv == result['obv_low']
    
    # 檢測背離
    result['divergence'] = 'none'
    
    # 頂背離: 價格新高，OBV 未新高（量能不支持）
    bearish_divergence = is_price_high & ~is_obv_high
    result.loc[bearish_divergence, 'divergence'] = 'bearish'
    
    # 底背離: 價格新低，OBV 未新低（下跌量能不足）
    bullish_divergence = is_price_low & ~is_obv_low
    result.loc[bullish_divergence, 'divergence'] = 'bullish'
    
    # 清理中間欄位
    result = result[['OBV', 'divergence']]
    
    return result


def calculate_obv_trend_strength(
    data: pd.DataFrame,
    short_period: int = 10,
    long_period: int = 30,
    close_column: str = 'close',
    volume_column: str = 'trading_volume'
) -> pd.DataFrame:
    """
    計算 OBV 趨勢強度
    
    使用雙均線系統判斷趨勢強度:
    - 短期均線 > 長期均線: 強勢多頭
    - 短期均線 < 長期均線: 強勢空頭
    - 均線交叉: 趨勢轉換訊號
    
    參數:
        data: 包含價格和成交量的 DataFrame
        short_period: 短期均線週期
        long_period: 長期均線週期
        close_column: 收盤價欄位
        volume_column: 成交量欄位
    
    返回:
        DataFrame: 包含 OBV 和趨勢強度
            - OBV: OBV 指標值
            - OBV_Short: 短期均線
            - OBV_Long: 長期均線
            - strength: strong_bullish=強多, weak_bullish=弱多,
                       strong_bearish=強空, weak_bearish=弱空
    """
    # 計算 OBV
    obv = calculate_obv(data, close_column, volume_column)
    
    # 計算短期和長期均線
    obv_short = obv.rolling(window=short_period).mean()
    obv_long = obv.rolling(window=long_period).mean()
    
    # 組合結果
    result = pd.DataFrame({
        'OBV': obv,
        'OBV_Short': obv_short,
        'OBV_Long': obv_long
    }, index=data.index)
    
    # 判斷趨勢強度
    result['strength'] = 'weak_bearish'
    
    # 強勢多頭: 短期 > 長期 且 OBV > 長期均線
    strong_bullish = (result['OBV_Short'] > result['OBV_Long']) & \
                     (result['OBV'] > result['OBV_Long'])
    result.loc[strong_bullish, 'strength'] = 'strong_bullish'
    
    # 弱勢多頭: 短期 > 長期 但 OBV < 長期均線
    weak_bullish = (result['OBV_Short'] > result['OBV_Long']) & \
                   (result['OBV'] <= result['OBV_Long'])
    result.loc[weak_bullish, 'strength'] = 'weak_bullish'
    
    # 強勢空頭: 短期 < 長期 且 OBV < 長期均線
    strong_bearish = (result['OBV_Short'] < result['OBV_Long']) & \
                     (result['OBV'] < result['OBV_Long'])
    result.loc[strong_bearish, 'strength'] = 'strong_bearish'
    
    return result


if __name__ == '__main__':
    # 測試範例
    import pandas as pd
    import numpy as np
    
    # 創建測試數據
    np.random.seed(42)
    n = 100
    
    # 模擬價格上漲 + 成交量放大
    prices = np.concatenate([
        np.linspace(100, 120, 50) + np.random.randn(50) * 1,
        np.linspace(120, 110, 50) + np.random.randn(50) * 1.5
    ])
    
    volumes = np.concatenate([
        np.linspace(1000, 2000, 50) + np.random.randn(50) * 100,  # 上漲放量
        np.linspace(2000, 1500, 50) + np.random.randn(50) * 150   # 下跌縮量
    ])
    
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=n),
        'close': prices,
        'trading_volume': volumes
    })
    
    # 測試 OBV 基本計算
    print("=" * 80)
    print("測試 OBV 基本計算")
    print("=" * 80)
    obv = calculate_obv(test_data)
    print(obv.tail(10))
    
    # 測試 OBV 訊號
    print("\n" + "=" * 80)
    print("測試 OBV 交易訊號")
    print("=" * 80)
    obv_signals = calculate_obv_signals(test_data)
    buy_signals = obv_signals[obv_signals['signal'] == 1]
    sell_signals = obv_signals[obv_signals['signal'] == -1]
    bullish = obv_signals[obv_signals['trend'] == 'bullish']
    
    print(f"買入訊號數量: {len(buy_signals)}")
    print(f"賣出訊號數量: {len(sell_signals)}")
    print(f"多頭天數: {len(bullish)}")
    print("\n最近的訊號:")
    print(obv_signals[obv_signals['signal'] != 0].tail())
    
    # 測試 OBV 背離
    print("\n" + "=" * 80)
    print("測試 OBV 背離")
    print("=" * 80)
    divergence = calculate_obv_divergence(test_data, lookback=20)
    bullish_div = divergence[divergence['divergence'] == 'bullish']
    bearish_div = divergence[divergence['divergence'] == 'bearish']
    print(f"底背離數量: {len(bullish_div)}")
    print(f"頂背離數量: {len(bearish_div)}")
    
    # 測試 OBV 趨勢強度
    print("\n" + "=" * 80)
    print("測試 OBV 趨勢強度")
    print("=" * 80)
    strength = calculate_obv_trend_strength(test_data)
    strong_bull = strength[strength['strength'] == 'strong_bullish']
    strong_bear = strength[strength['strength'] == 'strong_bearish']
    print(f"強勢多頭天數: {len(strong_bull)}")
    print(f"強勢空頭天數: {len(strong_bear)}")
    print("\n最近的強度:")
    print(strength.tail())
    
    print("\n✅ 所有測試完成")
