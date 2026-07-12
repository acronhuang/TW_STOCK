"""
SenVision 支撐壓力強度評估

演算法：
    Step 1: 利用 argrelextrema(order=5) 尋找局部高低點
    Step 2: 將 ±1% 誤差內的相近價格聚合成一個水平位
    Step 3: 統計每個水平位被 K 線觸碰的次數
    Step 4: 3次以上 → 強支撐/強壓力；2次 → 中等；1次 → 弱

規則：
    - 壓力位：在當前收盤價「上方」的阻力水平
    - 支撐位：在當前收盤價「下方」的支撐水平
    - 觸碰定義：K線的 High 進入帶狀區 或 K線的 Low 進入帶狀區

Author: SenVision Team
Date: 2026-02-24
"""

from typing import List, NamedTuple, Tuple

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


class SRLevel(NamedTuple):
    """支撐壓力水平位資料結構"""
    price: float           # 代表性價格
    type: str              # 'support' | 'resistance'
    touches: int           # 觸碰次數
    strength: str          # 'strong' | 'moderate' | 'weak'
    first_touch: int       # 第一次觸碰的 bar 索引（相對於傳入的 df_window）
    last_touch: int        # 最後一次觸碰的 bar 索引


def _find_pivot_prices(
    df: pd.DataFrame,
    order: int = 5
) -> Tuple[List[float], List[float]]:
    """
    利用 argrelextrema 找出局部高點價格與低點價格

    Args:
        df: OHLCV DataFrame
        order: 左右各 N 根 K 線確認轉折

    Returns:
        (resistance_prices, support_prices)
    """
    highs = df['high'].values
    lows = df['low'].values

    high_idxs = argrelextrema(highs, np.greater_equal, order=order)[0]
    low_idxs = argrelextrema(lows, np.less_equal, order=order)[0]

    return [highs[i] for i in high_idxs], [lows[i] for i in low_idxs]


def _cluster_prices(prices: List[float], tolerance: float = 0.01) -> List[float]:
    """
    將相近的價格（誤差 ≤ tolerance*2）聚合為單一代表價

    Args:
        prices: 待聚合的價格列表
        tolerance: 單邊容忍度（例如 0.01 = 1%，雙邊共 2%）

    Returns:
        聚合後的代表性價格列表
    """
    if not prices:
        return []

    sorted_prices = sorted(prices)
    clusters: List[List[float]] = []
    current: List[float] = [sorted_prices[0]]

    for p in sorted_prices[1:]:
        if current[-1] > 0 and abs(p - current[-1]) / current[-1] <= tolerance * 2:
            current.append(p)
        else:
            clusters.append(current)
            current = [p]
    clusters.append(current)

    return [float(np.mean(c)) for c in clusters]


def _count_touches(
    level_price: float,
    df: pd.DataFrame,
    tolerance: float = 0.01
) -> Tuple[int, int, int]:
    """
    計算 K 線觸碰指定價格帶的次數

    定義：K 線的 High >= band_low 且 Low <= band_high

    Args:
        level_price: 水平位價格
        df: OHLCV DataFrame
        tolerance: 單邊容忍度

    Returns:
        (touches_count, first_touch_idx, last_touch_idx)
    """
    band_low = level_price * (1.0 - tolerance)
    band_high = level_price * (1.0 + tolerance)

    touched = (df['high'] >= band_low) & (df['low'] <= band_high)
    touch_idxs = np.where(touched.values)[0]

    if len(touch_idxs) == 0:
        return 0, -1, -1
    return int(len(touch_idxs)), int(touch_idxs[0]), int(touch_idxs[-1])


def find_support_resistance(
    df: pd.DataFrame,
    order: int = 5,
    tolerance: float = 0.01,
    window: int = 100,
    min_touches_strong: int = 3,
    min_touches_moderate: int = 2,
) -> List[SRLevel]:
    """
    尋找支撐壓力位並評估強度

    Args:
        df: OHLCV DataFrame（含 high, low, close）
        order: argrelextrema 的 order（左右各 N 根）
        tolerance: 觸碰帶寬（±1%）
        window: 回看最近 N 根 K 線
        min_touches_strong: 「強」的最少觸碰次數（預設 3）
        min_touches_moderate: 「中」的最少觸碰次數（預設 2）

    Returns:
        SRLevel 列表，按價格由低到高排列
    """
    df_window = df.iloc[-window:].reset_index(drop=True)
    current_price = float(df_window['close'].iloc[-1])

    resistance_prices, support_prices = _find_pivot_prices(df_window, order=order)

    clustered_resistance = _cluster_prices(resistance_prices, tolerance)
    clustered_support = _cluster_prices(support_prices, tolerance)

    sr_levels: List[SRLevel] = []

    # ── 壓力位（在當前價格上方）
    for price in clustered_resistance:
        if price <= current_price * 0.995:   # 已被穿越，略過
            continue
        touches, first, last = _count_touches(price, df_window, tolerance)
        if touches < 1:
            continue
        strength = (
            'strong' if touches >= min_touches_strong else
            'moderate' if touches >= min_touches_moderate else
            'weak'
        )
        sr_levels.append(SRLevel(
            price=round(price, 2),
            type='resistance',
            touches=touches,
            strength=strength,
            first_touch=first,
            last_touch=last,
        ))

    # ── 支撐位（在當前價格下方）
    for price in clustered_support:
        if price >= current_price * 1.005:   # 已被跌破，略過
            continue
        touches, first, last = _count_touches(price, df_window, tolerance)
        if touches < 1:
            continue
        strength = (
            'strong' if touches >= min_touches_strong else
            'moderate' if touches >= min_touches_moderate else
            'weak'
        )
        sr_levels.append(SRLevel(
            price=round(price, 2),
            type='support',
            touches=touches,
            strength=strength,
            first_touch=first,
            last_touch=last,
        ))

    return sorted(sr_levels, key=lambda x: x.price)
