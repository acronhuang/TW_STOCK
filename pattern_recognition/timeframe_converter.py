#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多時間週期數據轉換模組
將日線數據轉換為週線、月線、季線、半年線、年線

作者: Ming
日期: 2026-02-24
版本: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TimeframeConverter:
    """時間週期轉換器"""

    # 支援的時間週期
    TIMEFRAMES = {
        'D': 'Daily',          # 日線
        'W': 'Weekly',         # 週線
        'M': 'Monthly',        # 月線
        'Q': 'Quarterly',      # 季線
        '6M': 'Semi-Annual',   # 半年線
        'Y': 'Yearly'          # 年線
    }

    # 重採樣規則
    RESAMPLE_RULES = {
        'D': 'D',
        'W': 'W-FRI',     # 週五收盤
        'M': 'M',         # 月底收盤
        'Q': 'Q',         # 季末收盤
        '6M': '6M',       # 半年末收盤
        'Y': 'Y'          # 年底收盤
    }

    def __init__(self):
        """初始化轉換器"""
        pass

    def convert_timeframe(
        self,
        df: pd.DataFrame,
        timeframe: str,
        include_volume: bool = True
    ) -> pd.DataFrame:
        """
        將日線數據轉換為指定時間週期

        參數:
            df: 日線數據（需包含 date, open, high, low, close, volume）
            timeframe: 目標時間週期 ('D', 'W', 'M', 'Q', '6M', 'Y')
            include_volume: 是否包含成交量

        返回:
            轉換後的 DataFrame
        """
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(
                f"不支援的時間週期: {timeframe}. "
                f"支援的選項: {list(self.TIMEFRAMES.keys())}"
            )

        # 如果是日線，直接返回
        if timeframe == 'D':
            return df.copy()

        try:
            # 確保 date 欄位為 datetime 索引
            df_work = df.copy()
            if 'date' in df_work.columns:
                df_work.set_index('date', inplace=True)

            # 確保索引為 DatetimeIndex
            if not isinstance(df_work.index, pd.DatetimeIndex):
                df_work.index = pd.to_datetime(df_work.index)

            # 排序
            df_work.sort_index(inplace=True)

            # 重採樣規則
            rule = self.RESAMPLE_RULES[timeframe]

            # OHLC 規則
            ohlc_dict = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            }

            if include_volume and 'volume' in df_work.columns:
                ohlc_dict['volume'] = 'sum'

            # 執行重採樣
            resampled = df_work.resample(rule).agg(ohlc_dict)

            # 移除空值（沒有交易的週期）
            resampled = resampled.dropna(subset=['close'])

            # 重置索引
            resampled.reset_index(inplace=True)

            logger.info(
                f"成功轉換: {len(df)} 筆日線數據 → "
                f"{len(resampled)} 筆{self.TIMEFRAMES[timeframe]}數據"
            )

            return resampled

        except Exception as e:
            logger.error(f"時間週期轉換失敗: {e}")
            raise

    def convert_multiple_timeframes(
        self,
        df: pd.DataFrame,
        timeframes: List[str]
    ) -> Dict[str, pd.DataFrame]:
        """
        將日線數據轉換為多個時間週期

        參數:
            df: 日線數據
            timeframes: 目標時間週期列表

        返回:
            字典，鍵為時間週期，值為對應的 DataFrame
        """
        result = {}

        for tf in timeframes:
            try:
                result[tf] = self.convert_timeframe(df, tf)
            except Exception as e:
                logger.error(f"轉換 {tf} 失敗: {e}")
                result[tf] = None

        return result

    def add_moving_averages(
        self,
        df: pd.DataFrame,
        periods: List[int] = [5, 10, 20, 60, 120, 240]
    ) -> pd.DataFrame:
        """
        添加移動平均線

        參數:
            df: 價格數據
            periods: MA 週期列表

        返回:
            添加了 MA 欄位的 DataFrame
        """
        df_ma = df.copy()

        for period in periods:
            col_name = f'ma_{period}'
            if len(df_ma) >= period:
                df_ma[col_name] = df_ma['close'].rolling(window=period).mean()
            else:
                logger.warning(
                    f"數據量不足以計算 MA{period}: "
                    f"需要 {period} 筆，實際 {len(df_ma)} 筆"
                )

        return df_ma

    def calculate_trend_slope(
        self,
        df: pd.DataFrame,
        column: str = 'close',
        window: int = 20
    ) -> pd.Series:
        """
        計算趨勢斜率（線性回歸斜率）

        參數:
            df: 價格數據
            column: 計算斜率的欄位
            window: 回歸窗口

        返回:
            斜率序列
        """
        slopes = []

        for i in range(len(df)):
            if i < window - 1:
                slopes.append(np.nan)
            else:
                # 取最近 window 筆數據
                y = df[column].iloc[i-window+1:i+1].values
                x = np.arange(window)

                # 線性回歸
                try:
                    slope, _ = np.polyfit(x, y, 1)
                    slopes.append(slope)
                except:
                    slopes.append(np.nan)

        return pd.Series(slopes, index=df.index)

    def detect_golden_cross(
        self,
        df: pd.DataFrame,
        short_period: int = 5,
        long_period: int = 20
    ) -> List[Dict]:
        """
        檢測黃金交叉（短均線上穿長均線）

        參數:
            df: 包含 MA 的價格數據
            short_period: 短週期 MA
            long_period: 長週期 MA

        返回:
            交叉點列表，每個包含 {date, type, short_ma, long_ma}
        """
        crosses = []

        short_col = f'ma_{short_period}'
        long_col = f'ma_{long_period}'

        if short_col not in df.columns or long_col not in df.columns:
            logger.warning("缺少必要的 MA 欄位")
            return crosses

        df_work = df.copy()

        # 計算差值
        df_work['ma_diff'] = df_work[short_col] - df_work[long_col]

        # 偵測交叉
        for i in range(1, len(df_work)):
            prev_diff = df_work['ma_diff'].iloc[i-1]
            curr_diff = df_work['ma_diff'].iloc[i]

            # 跳過 NaN
            if pd.isna(prev_diff) or pd.isna(curr_diff):
                continue

            # 黃金交叉（上穿）
            if prev_diff < 0 and curr_diff > 0:
                crosses.append({
                    'date': df_work['date'].iloc[i],
                    'type': 'golden_cross',
                    'short_ma': df_work[short_col].iloc[i],
                    'long_ma': df_work[long_col].iloc[i]
                })

            # 死亡交叉（下穿）
            elif prev_diff > 0 and curr_diff < 0:
                crosses.append({
                    'date': df_work['date'].iloc[i],
                    'type': 'death_cross',
                    'short_ma': df_work[short_col].iloc[i],
                    'long_ma': df_work[long_col].iloc[i]
                })

        return crosses

    def analyze_ma_alignment(
        self,
        df: pd.DataFrame,
        ma_periods: List[int] = [5, 20, 60, 120]
    ) -> str:
        """
        分析均線排列

        參數:
            df: 包含 MA 的價格數據
            ma_periods: 分析的 MA 週期

        返回:
            排列類型: 'bullish' (多頭排列), 'bearish' (空頭排列), 'neutral' (盤整)
        """
        if len(df) == 0:
            return 'neutral'

        # 取最新數據
        latest = df.iloc[-1]

        # 檢查所有 MA 是否存在
        ma_values = []
        for period in ma_periods:
            col = f'ma_{period}'
            if col in latest and not pd.isna(latest[col]):
                ma_values.append(float(latest[col]))
            else:
                return 'neutral'

        # 檢查是否為多頭排列（由小到大遞減）
        if all(ma_values[i] > ma_values[i+1] for i in range(len(ma_values)-1)):
            if 'close' in latest and float(latest['close']) > ma_values[0]:
                return 'bullish_strong'  # 強勢多頭（價格 > 所有MA）
            return 'bullish'

        # 檢查是否為空頭排列（由小到大遞增）
        if all(ma_values[i] < ma_values[i+1] for i in range(len(ma_values)-1)):
            if 'close' in latest and float(latest['close']) < ma_values[0]:
                return 'bearish_strong'  # 強勢空頭（價格 < 所有MA）
            return 'bearish'

        # 其他情況為盤整
        return 'neutral'

    def get_support_resistance(
        self,
        df: pd.DataFrame,
        lookback: int = 20,
        threshold: float = 0.02
    ) -> Dict[str, float]:
        """
        識別支撐和壓力位

        參數:
            df: 價格數據
            lookback: 回溯週期
            threshold: 價格接近閾值（百分比）

        返回:
            {'support': 支撐價, 'resistance': 壓力價}
        """
        if len(df) < lookback:
            return {'support': None, 'resistance': None}

        recent = df.tail(lookback)

        # 支撐：最低點
        support = recent['low'].min()

        # 壓力：最高點
        resistance = recent['high'].max()

        return {
            'support': float(support),
            'resistance': float(resistance)
        }


# 便捷函數
def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """快速轉換為週線"""
    converter = TimeframeConverter()
    return converter.convert_timeframe(df, 'W')


def resample_to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """快速轉換為月線"""
    converter = TimeframeConverter()
    return converter.convert_timeframe(df, 'M')


def resample_to_quarterly(df: pd.DataFrame) -> pd.DataFrame:
    """快速轉換為季線"""
    converter = TimeframeConverter()
    return converter.convert_timeframe(df, 'Q')


if __name__ == '__main__':
    # 測試
    print("時間週期轉換模組已載入")
    print(f"支援的時間週期: {list(TimeframeConverter.TIMEFRAMES.keys())}")
