#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支撐壓力與頸線識別模組
基於蔡森形態學的量化實作

功能:
1. 轉折點識別（ZigZag演算法）
2. 水平頸線自動識別
3. 趨勢切線擬合（破切分析）
4. 突破偵測與量能確認
5. 支撐壓力強度評估

作者: Ming
日期: 2026-02-24
版本: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


@dataclass
class PivotPoint:
    """轉折點數據類"""
    index: int          # 在DataFrame中的索引
    date: datetime      # 日期
    price: float        # 價格
    type: str          # 'high' or 'low'
    strength: int = 0   # 強度（觸碰次數）


@dataclass
class SupportResistance:
    """支撐壓力數據類"""
    price: float           # 價格水平
    type: str             # 'support' or 'resistance'
    strength: int         # 強度（觸碰次數）
    touches: List[int]    # 觸碰點的索引列表
    first_date: datetime  # 首次出現日期
    last_date: datetime   # 最後觸碰日期
    is_broken: bool = False  # 是否已突破


@dataclass
class Neckline:
    """頸線數據類"""
    price: float          # 頸線價格
    type: str            # 'W_bottom' or 'M_top'
    left_pivot: int      # 左側轉折點索引
    middle_pivot: int    # 中間轉折點索引
    right_pivot: int     # 右側轉折點索引
    is_broken: bool = False  # 是否已突破
    breakout_date: Optional[datetime] = None
    breakout_volume_confirmed: bool = False


@dataclass
class Trendline:
    """趨勢線數據類"""
    slope: float          # 斜率
    intercept: float      # 截距
    type: str            # 'ascending' or 'descending'
    points: List[int]    # 用於擬合的點索引
    start_date: datetime
    end_date: datetime
    is_broken: bool = False


class PivotIdentifier:
    """轉折點識別器（ZigZag演算法）"""

    def __init__(self, order: int = 5, threshold: float = 0.02):
        """
        初始化

        參數:
            order: 局部極值的窗口大小（左右各order根K線）
            threshold: 價格變動閾值（百分比），過濾小波動
        """
        self.order = order
        self.threshold = threshold

    def find_pivots(self, df: pd.DataFrame) -> Tuple[List[PivotPoint], List[PivotPoint]]:
        """
        尋找轉折點（高點和低點）

        參數:
            df: 包含high, low, date的DataFrame

        返回:
            (高點列表, 低點列表)
        """
        highs = []
        lows = []

        # 使用scipy找局部極值
        high_indices = argrelextrema(df['high'].values, np.greater, order=self.order)[0]
        low_indices = argrelextrema(df['low'].values, np.less, order=self.order)[0]

        # 過濾小波動（可選）
        if self.threshold > 0:
            high_indices = self._filter_by_threshold(
                df, high_indices, 'high', 'greater'
            )
            low_indices = self._filter_by_threshold(
                df, low_indices, 'low', 'less'
            )

        # 構建PivotPoint對象
        for idx in high_indices:
            highs.append(PivotPoint(
                index=idx,
                date=df.iloc[idx]['date'],
                price=df.iloc[idx]['high'],
                type='high'
            ))

        for idx in low_indices:
            lows.append(PivotPoint(
                index=idx,
                date=df.iloc[idx]['date'],
                price=df.iloc[idx]['low'],
                type='low'
            ))

        logger.info(f"找到 {len(highs)} 個高點, {len(lows)} 個低點")

        return highs, lows

    def _filter_by_threshold(
        self,
        df: pd.DataFrame,
        indices: np.ndarray,
        column: str,
        comparison: str
    ) -> np.ndarray:
        """
        過濾不顯著的轉折點

        參數:
            df: 數據
            indices: 候選索引
            column: 欄位名稱
            comparison: 'greater' 或 'less'

        返回:
            過濾後的索引
        """
        if len(indices) == 0:
            return indices

        filtered = []
        values = df[column].values

        for i, idx in enumerate(indices):
            if i == 0:
                filtered.append(idx)
                continue

            prev_idx = filtered[-1]
            prev_value = values[prev_idx]
            curr_value = values[idx]

            # 計算變動百分比
            change_pct = abs(curr_value - prev_value) / prev_value

            # 只保留顯著變動
            if change_pct >= self.threshold:
                filtered.append(idx)

        return np.array(filtered)

    def find_zigzag_pivots(
        self,
        df: pd.DataFrame,
        min_change_pct: float = 0.05
    ) -> List[PivotPoint]:
        """
        ZigZag演算法尋找顯著轉折點

        參數:
            df: 價格數據
            min_change_pct: 最小波動百分比（例如0.05代表5%）

        返回:
            轉折點列表（按時間順序，高低點交替）
        """
        if len(df) < 3:
            return []

        pivots = []
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # 找第一個轉折點
        first_high = high[0]
        first_low = low[0]

        # 判斷趨勢方向
        if close[2] > close[0]:
            # 上升趨勢，從低點開始
            current_pivot = PivotPoint(
                index=0,
                date=df.iloc[0]['date'],
                price=first_low,
                type='low'
            )
        else:
            # 下降趨勢，從高點開始
            current_pivot = PivotPoint(
                index=0,
                date=df.iloc[0]['date'],
                price=first_high,
                type='high'
            )

        pivots.append(current_pivot)

        # 遍歷數據尋找顯著轉折
        for i in range(1, len(df)):
            if current_pivot.type == 'low':
                # 尋找下一個高點
                if high[i] > current_pivot.price * (1 + min_change_pct):
                    # 找到顯著高點
                    # 回溯找最高點
                    peak_idx = i
                    peak_price = high[i]

                    for j in range(current_pivot.index + 1, i + 1):
                        if high[j] > peak_price:
                            peak_idx = j
                            peak_price = high[j]

                    current_pivot = PivotPoint(
                        index=peak_idx,
                        date=df.iloc[peak_idx]['date'],
                        price=peak_price,
                        type='high'
                    )
                    pivots.append(current_pivot)

            else:  # current_pivot.type == 'high'
                # 尋找下一個低點
                if low[i] < current_pivot.price * (1 - min_change_pct):
                    # 找到顯著低點
                    # 回溯找最低點
                    trough_idx = i
                    trough_price = low[i]

                    for j in range(current_pivot.index + 1, i + 1):
                        if low[j] < trough_price:
                            trough_idx = j
                            trough_price = low[j]

                    current_pivot = PivotPoint(
                        index=trough_idx,
                        date=df.iloc[trough_idx]['date'],
                        price=trough_price,
                        type='low'
                    )
                    pivots.append(current_pivot)

        logger.info(f"ZigZag找到 {len(pivots)} 個顯著轉折點")

        return pivots


class NecklineDetector:
    """頸線識別器"""

    def __init__(self, tolerance: float = 0.03):
        """
        初始化

        參數:
            tolerance: 價格容忍度（百分比）
        """
        self.tolerance = tolerance

    def detect_w_bottom_neckline(
        self,
        df: pd.DataFrame,
        pivots: List[PivotPoint]
    ) -> List[Neckline]:
        """
        識別W底頸線

        參數:
            df: 價格數據
            pivots: 轉折點列表

        返回:
            頸線列表
        """
        necklines = []

        # 過濾出低點
        lows = [p for p in pivots if p.type == 'low']

        # 需要至少2個低點
        if len(lows) < 2:
            return necklines

        # 遍歷尋找W底結構
        for i in range(len(lows) - 1):
            left_low = lows[i]
            right_low = lows[i + 1]

            # 檢查兩個低點是否接近（誤差容忍）
            price_diff = abs(left_low.price - right_low.price) / left_low.price

            if price_diff > self.tolerance:
                continue

            # 找中間的高點（頸線）
            middle_high = self._find_middle_peak(
                df, left_low.index, right_low.index
            )

            if middle_high is None:
                continue

            # 檢查頸線是否有效（高於兩個低點）
            avg_low = (left_low.price + right_low.price) / 2
            if middle_high.price < avg_low * 1.02:  # 至少高於2%
                continue

            # 創建頸線
            neckline = Neckline(
                price=middle_high.price,
                type='W_bottom',
                left_pivot=left_low.index,
                middle_pivot=middle_high.index,
                right_pivot=right_low.index
            )

            # 檢查是否已突破
            current_price = df.iloc[-1]['close']
            if current_price > neckline.price:
                neckline.is_broken = True
                # 尋找突破日期
                breakout_idx = self._find_breakout_index(
                    df, middle_high.index, neckline.price, 'upward'
                )
                if breakout_idx is not None:
                    neckline.breakout_date = df.iloc[breakout_idx]['date']
                    # 檢查量能
                    neckline.breakout_volume_confirmed = self._check_volume_confirmation(
                        df, breakout_idx
                    )

            necklines.append(neckline)

        logger.info(f"找到 {len(necklines)} 個W底頸線")
        return necklines

    def detect_m_top_neckline(
        self,
        df: pd.DataFrame,
        pivots: List[PivotPoint]
    ) -> List[Neckline]:
        """
        識別M頭頸線

        參數:
            df: 價格數據
            pivots: 轉折點列表

        返回:
            頸線列表
        """
        necklines = []

        # 過濾出高點
        highs = [p for p in pivots if p.type == 'high']

        # 需要至少2個高點
        if len(highs) < 2:
            return necklines

        # 遍歷尋找M頭結構
        for i in range(len(highs) - 1):
            left_high = highs[i]
            right_high = highs[i + 1]

            # 檢查兩個高點是否接近
            price_diff = abs(left_high.price - right_high.price) / left_high.price

            if price_diff > self.tolerance:
                continue

            # 找中間的低點（頸線）
            middle_low = self._find_middle_trough(
                df, left_high.index, right_high.index
            )

            if middle_low is None:
                continue

            # 檢查頸線是否有效（低於兩個高點）
            avg_high = (left_high.price + right_high.price) / 2
            if middle_low.price > avg_high * 0.98:  # 至少低於2%
                continue

            # 創建頸線
            neckline = Neckline(
                price=middle_low.price,
                type='M_top',
                left_pivot=left_high.index,
                middle_pivot=middle_low.index,
                right_pivot=right_high.index
            )

            # 檢查是否已突破
            current_price = df.iloc[-1]['close']
            if current_price < neckline.price:
                neckline.is_broken = True
                # 尋找突破日期
                breakout_idx = self._find_breakout_index(
                    df, middle_low.index, neckline.price, 'downward'
                )
                if breakout_idx is not None:
                    neckline.breakout_date = df.iloc[breakout_idx]['date']
                    neckline.breakout_volume_confirmed = self._check_volume_confirmation(
                        df, breakout_idx
                    )

            necklines.append(neckline)

        logger.info(f"找到 {len(necklines)} 個M頭頸線")
        return necklines

    def _find_middle_peak(
        self,
        df: pd.DataFrame,
        left_idx: int,
        right_idx: int
    ) -> Optional[PivotPoint]:
        """找中間最高點"""
        if right_idx <= left_idx:
            return None

        segment = df.iloc[left_idx:right_idx+1]
        peak_idx = segment['high'].idxmax()

        return PivotPoint(
            index=peak_idx,
            date=df.iloc[peak_idx]['date'],
            price=df.iloc[peak_idx]['high'],
            type='high'
        )

    def _find_middle_trough(
        self,
        df: pd.DataFrame,
        left_idx: int,
        right_idx: int
    ) -> Optional[PivotPoint]:
        """找中間最低點"""
        if right_idx <= left_idx:
            return None

        segment = df.iloc[left_idx:right_idx+1]
        trough_idx = segment['low'].idxmin()

        return PivotPoint(
            index=trough_idx,
            date=df.iloc[trough_idx]['date'],
            price=df.iloc[trough_idx]['low'],
            type='low'
        )

    def _find_breakout_index(
        self,
        df: pd.DataFrame,
        start_idx: int,
        neckline_price: float,
        direction: str
    ) -> Optional[int]:
        """找突破點索引"""
        for i in range(start_idx, len(df)):
            close = df.iloc[i]['close']

            if direction == 'upward' and close > neckline_price:
                return i
            elif direction == 'downward' and close < neckline_price:
                return i

        return None

    def _check_volume_confirmation(
        self,
        df: pd.DataFrame,
        breakout_idx: int,
        lookback: int = 5
    ) -> bool:
        """
        檢查突破時的量能確認

        參數:
            df: 數據
            breakout_idx: 突破點索引
            lookback: 回溯天數

        返回:
            是否有量能確認
        """
        if 'volume' not in df.columns:
            return False

        if breakout_idx < lookback:
            return False

        # 突破日量能
        breakout_volume = df.iloc[breakout_idx]['volume']

        # 前N日平均量能
        avg_volume = df.iloc[breakout_idx-lookback:breakout_idx]['volume'].mean()

        # 判斷是否放量（1.5倍）
        return breakout_volume > avg_volume * 1.5


class TrendlineDetector:
    """趨勢線識別器（破切分析）"""

    def __init__(self, min_points: int = 2):
        """
        初始化

        參數:
            min_points: 最少需要的點數
        """
        self.min_points = min_points

    def detect_descending_trendline(
        self,
        df: pd.DataFrame,
        pivots: List[PivotPoint],
        lookback: int = 60
    ) -> List[Trendline]:
        """
        識別下降趨勢線（多方破切）

        參數:
            df: 價格數據
            pivots: 轉折點列表
            lookback: 回溯天數

        返回:
            趨勢線列表
        """
        trendlines = []

        # 過濾出高點
        highs = [p for p in pivots if p.type == 'high']

        # 過濾最近的高點
        recent_highs = [h for h in highs if h.index >= len(df) - lookback]

        if len(recent_highs) < self.min_points:
            return trendlines

        # 尋找下降的高點序列
        for i in range(len(recent_highs) - 1):
            h1 = recent_highs[i]
            h2 = recent_highs[i + 1]

            # 確認是下降趨勢
            if h2.price >= h1.price:
                continue

            # 線性擬合
            x = np.array([h1.index, h2.index])
            y = np.array([h1.price, h2.price])
            coeffs = np.polyfit(x, y, 1)
            slope, intercept = coeffs

            # 檢查斜率（必須為負）
            if slope >= 0:
                continue

            trendline = Trendline(
                slope=slope,
                intercept=intercept,
                type='descending',
                points=[h1.index, h2.index],
                start_date=h1.date,
                end_date=h2.date
            )

            # 檢查是否已突破
            current_price = df.iloc[-1]['close']
            current_idx = len(df) - 1
            trendline_price = slope * current_idx + intercept

            if current_price > trendline_price:
                trendline.is_broken = True

            trendlines.append(trendline)

        logger.info(f"找到 {len(trendlines)} 條下降趨勢線")
        return trendlines

    def detect_ascending_trendline(
        self,
        df: pd.DataFrame,
        pivots: List[PivotPoint],
        lookback: int = 60
    ) -> List[Trendline]:
        """
        識別上升趨勢線（空方破切）

        參數:
            df: 價格數據
            pivots: 轉折點列表
            lookback: 回溯天數

        返回:
            趨勢線列表
        """
        trendlines = []

        # 過濾出低點
        lows = [p for p in pivots if p.type == 'low']

        # 過濾最近的低點
        recent_lows = [l for l in lows if l.index >= len(df) - lookback]

        if len(recent_lows) < self.min_points:
            return trendlines

        # 尋找上升的低點序列
        for i in range(len(recent_lows) - 1):
            l1 = recent_lows[i]
            l2 = recent_lows[i + 1]

            # 確認是上升趨勢
            if l2.price <= l1.price:
                continue

            # 線性擬合
            x = np.array([l1.index, l2.index])
            y = np.array([l1.price, l2.price])
            coeffs = np.polyfit(x, y, 1)
            slope, intercept = coeffs

            # 檢查斜率（必須為正）
            if slope <= 0:
                continue

            trendline = Trendline(
                slope=slope,
                intercept=intercept,
                type='ascending',
                points=[l1.index, l2.index],
                start_date=l1.date,
                end_date=l2.date
            )

            # 檢查是否已突破
            current_price = df.iloc[-1]['close']
            current_idx = len(df) - 1
            trendline_price = slope * current_idx + intercept

            if current_price < trendline_price:
                trendline.is_broken = True

            trendlines.append(trendline)

        logger.info(f"找到 {len(trendlines)} 條上升趨勢線")
        return trendlines


class SupportResistanceDetector:
    """支撐壓力識別器"""

    def __init__(self, tolerance: float = 0.01, min_touches: int = 2):
        """
        初始化

        參數:
            tolerance: 價格容忍度（百分比）
            min_touches: 最少觸碰次數
        """
        self.tolerance = tolerance
        self.min_touches = min_touches

    def detect_levels(
        self,
        df: pd.DataFrame,
        pivots: List[PivotPoint],
        lookback: int = 100
    ) -> List[SupportResistance]:
        """
        識別支撐壓力水平

        參數:
            df: 價格數據
            pivots: 轉折點列表
            lookback: 回溯天數

        返回:
            支撐壓力列表
        """
        levels = []

        # 過濾最近的轉折點
        recent_pivots = [p for p in pivots if p.index >= len(df) - lookback]

        if not recent_pivots:
            return levels

        # 聚類相似價格
        clusters = self._cluster_prices(recent_pivots)

        # 為每個cluster創建支撐/壓力
        for cluster in clusters:
            if len(cluster) < self.min_touches:
                continue

            # 計算平均價格
            avg_price = np.mean([p.price for p in cluster])

            # 判斷類型（支撐或壓力）
            types = [p.type for p in cluster]
            if types.count('low') > types.count('high'):
                level_type = 'support'
            else:
                level_type = 'resistance'

            # 創建支撐/壓力對象
            level = SupportResistance(
                price=avg_price,
                type=level_type,
                strength=len(cluster),
                touches=[p.index for p in cluster],
                first_date=min(p.date for p in cluster),
                last_date=max(p.date for p in cluster)
            )

            # 檢查是否已突破
            current_price = df.iloc[-1]['close']
            if level_type == 'support' and current_price < avg_price * 0.98:
                level.is_broken = True
            elif level_type == 'resistance' and current_price > avg_price * 1.02:
                level.is_broken = True

            levels.append(level)

        # 按強度排序
        levels.sort(key=lambda x: x.strength, reverse=True)

        logger.info(f"找到 {len(levels)} 個支撐壓力水平")
        return levels

    def _cluster_prices(
        self,
        pivots: List[PivotPoint]
    ) -> List[List[PivotPoint]]:
        """
        將相似價格聚類

        參數:
            pivots: 轉折點列表

        返回:
            聚類列表
        """
        if not pivots:
            return []

        # 按價格排序
        sorted_pivots = sorted(pivots, key=lambda p: p.price)

        clusters = []
        current_cluster = [sorted_pivots[0]]

        for i in range(1, len(sorted_pivots)):
            pivot = sorted_pivots[i]
            prev_pivot = current_cluster[-1]

            # 檢查價格是否接近
            price_diff = abs(pivot.price - prev_pivot.price) / prev_pivot.price

            if price_diff <= self.tolerance:
                # 加入當前cluster
                current_cluster.append(pivot)
            else:
                # 開始新cluster
                clusters.append(current_cluster)
                current_cluster = [pivot]

        # 加入最後一個cluster
        if current_cluster:
            clusters.append(current_cluster)

        return clusters


if __name__ == '__main__':
    print("支撐壓力與頸線識別模組已載入")
    print("功能: 轉折點識別、頸線檢測、趨勢線擬合、支撐壓力分析")
