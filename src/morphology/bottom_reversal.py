"""
破底翻 (Bottom Reversal) 形態偵測

定義：股價跌破前波低點（支撐線）後，於 5 日內帶量收復。

量化條件：
1. low[0] < support_line（當日最低價跌破支撐線）
2. close[0] > support_line * 1.02（收盤價站回支撐線 +2%）
3. volume[0] > mean(volume, 5) * 1.5（成交量放大 1.5 倍）
4. 上述條件需在 5 個交易日內完成

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional


def detect_bottom_reversal(
    df: pd.DataFrame,
    window: int = 20,
    recovery_days: int = 5,
    volume_ratio: float = 1.5,
    recovery_threshold: float = 1.02
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    偵測破底翻形態
    
    Args:
        df: DataFrame，必須包含 open, high, low, close, volume 欄位
        window: 支撐線計算週期（預設 20 日）
        recovery_days: 允許的收復天數（預設 5 日）
        volume_ratio: 成交量放大倍數（預設 1.5 倍）
        recovery_threshold: 收復閾值（預設 1.02，即支撐線 +2%）
    
    Returns:
        Tuple[pd.Series, pd.DataFrame]:
            - signal: Boolean Series，True 表示出現破底翻
            - details: DataFrame，包含形態詳細資訊
    """
    # 輸入驗證
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"DataFrame 必須包含 {required_cols} 欄位")
    
    if len(df) < window + recovery_days:
        # 數據不足，返回全 False
        return pd.Series(False, index=df.index), pd.DataFrame()
    
    # 計算支撐線（20 日最低價的滾動最低）
    support_line = df['low'].rolling(window).min().shift(1)
    
    # 計算 5 日平均成交量
    avg_volume = df['volume'].rolling(5).mean()
    
    # 初始化結果
    signal = pd.Series(False, index=df.index)
    details_list = []
    
    # 逐日檢查破底翻形態
    for i in range(window + recovery_days, len(df)):
        # 檢查過去 recovery_days 天是否出現破底翻
        for j in range(max(0, i - recovery_days + 1), i + 1):
            if pd.isna(support_line.iloc[j]) or pd.isna(avg_volume.iloc[j]):
                continue
            
            support = support_line.iloc[j]
            
            # 條件 1: 跌破支撐線
            broke_support = df['low'].iloc[j] < support
            
            if not broke_support:
                continue
            
            # 檢查後續是否收復
            for k in range(j, min(j + recovery_days, len(df))):
                # 條件 2: 收盤站回支撐線 +2%
                recovered = df['close'].iloc[k] > support * recovery_threshold
                
                # 條件 3: 成交量放大
                volume_surge = df['volume'].iloc[k] > avg_volume.iloc[k] * volume_ratio
                
                if recovered and volume_surge:
                    # 找到破底翻形態
                    signal.iloc[k] = True
                    
                    # 計算形態強度評分（0-1）
                    recovery_speed = 1.0 - (k - j) / recovery_days  # 越快收復越好
                    volume_strength = min(df['volume'].iloc[k] / (avg_volume.iloc[k] * volume_ratio), 2.0) / 2.0
                    price_strength = min((df['close'].iloc[k] - support) / support / 0.05, 1.0)
                    
                    pattern_score = (recovery_speed * 0.4 + volume_strength * 0.4 + price_strength * 0.2)
                    
                    details_list.append({
                        'date': df.index[k],
                        'pattern': 'bottom_reversal',
                        'support_line': support,
                        'low_price': df['low'].iloc[j],
                        'recovery_price': df['close'].iloc[k],
                        'volume_ratio': df['volume'].iloc[k] / avg_volume.iloc[k],
                        'days_to_recover': k - j,
                        'pattern_score': round(pattern_score, 3)
                    })
                    
                    break  # 找到後跳出
    
    # 轉換為 DataFrame
    details_df = pd.DataFrame(details_list)
    if not details_df.empty:
        details_df.set_index('date', inplace=True)
    
    return signal, details_df


def check_pattern_breakdown(
    current_price: float,
    support_line: float,
    entry_price: float,
    recent_closes: pd.Series,
    recent_volumes: pd.Series
) -> Tuple[bool, Optional[str]]:
    """
    檢查破底翻形態是否破壞（用於出場判斷）
    
    Args:
        current_price: 當前收盤價
        support_line: 支撐線價格
        entry_price: 進場價格
        recent_closes: 近期收盤價（至少 3 日）
        recent_volumes: 近期成交量（至少 3 日）
    
    Returns:
        Tuple[bool, Optional[str]]:
            - is_broken: 是否破壞
            - reason: 破壞原因
    """
    # 破壞條件 1: 跌破支撐線 -2%
    if current_price < support_line * 0.98:
        return True, "跌破支撐線 -2%"
    
    # 破壞條件 2: 單日大跌 -7%
    if (current_price - entry_price) / entry_price < -0.07:
        return True, "單日大跌 -7%"
    
    # 破壞條件 3: 連續 3 日收黑且縮量
    if len(recent_closes) >= 3 and len(recent_volumes) >= 3:
        all_red = all(recent_closes.diff().dropna() < 0)
        avg_volume = recent_volumes.mean()
        volume_shrink = all(recent_volumes < avg_volume * 0.7)
        
        if all_red and volume_shrink:
            return True, "連續 3 日收黑且縮量"
    
    return False, None


def calculate_stop_loss(entry_price: float, support_line: float) -> float:
    """
    計算破底翻的止損價格
    
    Args:
        entry_price: 進場價格
        support_line: 支撐線價格
    
    Returns:
        float: 止損價格（支撐線 -2% 與 進場價 -5% 取較大者）
    """
    support_stop = support_line * 0.98
    fixed_stop = entry_price * 0.95
    
    return max(support_stop, fixed_stop)


if __name__ == "__main__":
    # 測試範例
    print("破底翻形態偵測模組測試")
    print("=" * 60)
    
    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-03-31', freq='D')
    np.random.seed(42)
    
    # 模擬破底翻：先跌破後收復
    prices = np.concatenate([
        np.linspace(100, 80, 40),  # 下跌
        np.array([78, 76, 75]),    # 跌破支撐（80）
        np.array([82, 85, 87]),    # 帶量收復
        np.linspace(87, 95, 20)    # 上漲
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 40),
        np.array([1500, 1800, 2000]),  # 跌破時
        np.array([5000, 6000, 5500]),  # 收復時大量
        np.random.uniform(2000, 3000, 20)
    ])
    
    df = pd.DataFrame({
        'open': prices * 1.01,
        'high': prices * 1.02,
        'low': prices * 0.98,
        'close': prices,
        'volume': volumes
    }, index=dates[:len(prices)])
    
    # 執行偵測
    signal, details = detect_bottom_reversal(df)
    
    print(f"\n找到 {signal.sum()} 個破底翻形態")
    if not details.empty:
        print("\n形態詳細資訊：")
        print(details.to_string())
    
    # 測試止損計算
    if not details.empty:
        first_pattern = details.iloc[0]
        stop_price = calculate_stop_loss(
            entry_price=first_pattern['recovery_price'],
            support_line=first_pattern['support_line']
        )
        print(f"\n止損價格: {stop_price:.2f}")
