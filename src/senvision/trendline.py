"""
SenVision 趨勢切線自動識別（破切）

蔡森老師「破切」神招定義：
    - 下降切線（待向上突破）：連結最近兩個下降的高點 H1 > H2
    - 上升切線（待向下突破）：連結最近兩個上升的低點 L1 < L2

有效突破條件（F4 規格）：
    1. Close[t] 穿越切線（上方或下方）
    2. 穿越幅度 ≥ 0.5%（避免假突破）
    3. 突破當日成交量 ≥ 前 5 日均量 × 1.5

Author: SenVision Team
Date: 2026-02-24
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd

from .zigzag import Peak


@dataclass
class Trendline:
    """
    趨勢切線資料結構

    Attributes:
        type: 'descending_resistance' | 'ascending_support'
        p1: 第一個錨點（較早的轉折點）
        p2: 第二個錨點（較新的轉折點）
        slope: 斜率（每根 bar 的價格變化）
        is_broken: 是否已發生有效突破
        break_index: 突破 bar 的索引
        break_date: 突破日期
        break_price: 突破時的收盤價
    """
    type: str
    p1: Peak
    p2: Peak
    slope: float
    is_broken: bool = False
    break_index: Optional[int] = None
    break_date: Optional[datetime] = None
    break_price: Optional[float] = None

    def price_at(self, bar_index: int) -> float:
        """計算切線在指定 bar 索引處的理論價格"""
        return self.p1.price + self.slope * (bar_index - self.p1.index)

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'p1_date': self.p1.date.isoformat(),
            'p1_price': self.p1.price,
            'p2_date': self.p2.date.isoformat(),
            'p2_price': self.p2.price,
            'slope': round(self.slope, 4),
            'is_broken': self.is_broken,
            'break_date': self.break_date.isoformat() if self.break_date else None,
            'break_price': self.break_price,
        }


def find_descending_resistance(
    peaks: List[Peak],
    min_separation: int = 5,
    max_lines: int = 2,
) -> List[Trendline]:
    """
    尋找下降壓力切線（連結高點 H1 > H2）

    從最新的高點往前搜尋，只保留最近的幾條。

    Args:
        peaks: ZigZag 轉折點（含 H 和 L）
        min_separation: 兩個高點之間的最小 bar 距離
        max_lines: 最多返回幾條切線

    Returns:
        下降切線列表（按新舊排序，最新在前）
    """
    highs = [p for p in peaks if p.type == 'H']
    trendlines: List[Trendline] = []

    for i in range(len(highs) - 1, 0, -1):
        H2 = highs[i]      # 較新
        H1 = highs[i - 1]  # 較舊

        if H2.price >= H1.price:
            continue
        if (H2.index - H1.index) < min_separation:
            continue

        slope = (H2.price - H1.price) / (H2.index - H1.index)
        trendlines.append(Trendline(
            type='descending_resistance',
            p1=H1,
            p2=H2,
            slope=slope,
        ))

        if len(trendlines) >= max_lines:
            break

    return trendlines


def find_ascending_support(
    peaks: List[Peak],
    min_separation: int = 5,
    max_lines: int = 2,
) -> List[Trendline]:
    """
    尋找上升支撐切線（連結低點 L1 < L2）

    Args:
        peaks: ZigZag 轉折點
        min_separation: 兩個低點之間的最小 bar 距離
        max_lines: 最多返回幾條切線

    Returns:
        上升切線列表（最新在前）
    """
    lows = [p for p in peaks if p.type == 'L']
    trendlines: List[Trendline] = []

    for i in range(len(lows) - 1, 0, -1):
        L2 = lows[i]
        L1 = lows[i - 1]

        if L2.price <= L1.price:
            continue
        if (L2.index - L1.index) < min_separation:
            continue

        slope = (L2.price - L1.price) / (L2.index - L1.index)
        trendlines.append(Trendline(
            type='ascending_support',
            p1=L1,
            p2=L2,
            slope=slope,
        ))

        if len(trendlines) >= max_lines:
            break

    return trendlines


def detect_trendline_break(
    df: pd.DataFrame,
    trendlines: List[Trendline],
    min_breakout_pct: float = 0.005,
    volume_ratio: float = 1.5,
    volume_ma_period: int = 5,
) -> List[Trendline]:
    """
    偵測切線是否已發生有效突破（原地修改 is_broken 等欄位）

    有效突破條件（F4）：
        1. 前一根 close <= 切線價格；當根 close > 切線 × (1 + min_breakout_pct)
        2. 突破量 ≥ 前 N 日均量 × volume_ratio

    Args:
        df: OHLCV DataFrame（含 date, close, volume）
        trendlines: 切線列表（會被原地修改）
        min_breakout_pct: 最小突破幅度（0.005 = 0.5%）
        volume_ratio: 量能確認倍數（1.5 倍均量）
        volume_ma_period: 均量計算週期

    Returns:
        更新後的切線列表（同一物件）
    """
    if df.empty or not trendlines:
        return trendlines

    closes = df['close'].values
    volumes = df['volume'].values
    dates = pd.to_datetime(df['date'] if 'date' in df.columns else df.index)

    vol_ma = pd.Series(volumes).rolling(volume_ma_period, min_periods=1).mean().values

    for tl in trendlines:
        start_check = tl.p2.index + 1

        for i in range(start_check, len(df)):
            tl_price = tl.price_at(i)
            close = closes[i]
            prev_close = closes[i - 1] if i > 0 else close
            prev_tl = tl.price_at(i - 1)

            if tl.type == 'descending_resistance':
                # 向上突破：前日在線下，今日收盤超過切線 + 0.5%
                if prev_close <= prev_tl and close > tl_price * (1.0 + min_breakout_pct):
                    vol_ok = (
                        volumes[i] >= vol_ma[i - 1] * volume_ratio
                        if i >= volume_ma_period and vol_ma[i - 1] > 0
                        else True
                    )
                    if vol_ok:
                        tl.is_broken = True
                        tl.break_index = i
                        tl.break_date = dates.iloc[i]
                        tl.break_price = float(close)
                        break

            elif tl.type == 'ascending_support':
                # 向下突破：前日在線上，今日收盤跌破切線 - 0.5%
                if prev_close >= prev_tl and close < tl_price * (1.0 - min_breakout_pct):
                    vol_ok = (
                        volumes[i] >= vol_ma[i - 1] * volume_ratio
                        if i >= volume_ma_period and vol_ma[i - 1] > 0
                        else True
                    )
                    if vol_ok:
                        tl.is_broken = True
                        tl.break_index = i
                        tl.break_date = dates.iloc[i]
                        tl.break_price = float(close)
                        break

    return trendlines
