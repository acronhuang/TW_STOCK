"""
SenVision 多時間框架支援

將日線 OHLCV 重採樣至不同時間框架：
    日(D)、週(W)、月(M)、季(Q)、半年(6M)、年(Y)

ZigZag 閾值與形態寬度會依時間框架自動調整。

Author: SenVision Team
Date: 2026-02-24
"""

from typing import Literal, Tuple

import numpy as np
import pandas as pd

# ── 支援的時間框架 ──────────────────────────────────────────────────────────────
TimeFrame = Literal['D', 'W', 'M', 'Q', '6M', 'Y']

TIMEFRAME_CONFIG: dict = {
    'D': {
        'freq': None,       # 不重採樣，直接使用日線
        'label': '日線',
        'zigzag_threshold': 0.05,
        'min_width_bars': 10,
        'max_width_bars': 60,
        'candle_width_days': 0.6,
    },
    'W': {
        'freq': 'W-FRI',    # 以週五為週末
        'label': '週線',
        'zigzag_threshold': 0.08,
        'min_width_bars': 6,
        'max_width_bars': 26,
        'candle_width_days': 3.5,
    },
    'M': {
        'freq': 'ME',       # Month End
        'label': '月線',
        'zigzag_threshold': 0.10,
        'min_width_bars': 3,
        'max_width_bars': 12,
        'candle_width_days': 15,
    },
    'Q': {
        'freq': 'QE',       # Quarter End
        'label': '季線',
        'zigzag_threshold': 0.12,
        'min_width_bars': 2,
        'max_width_bars': 6,
        'candle_width_days': 45,
    },
    '6M': {
        'freq': '6ME',      # 每 6 個月末
        'label': '半年線',
        'zigzag_threshold': 0.15,
        'min_width_bars': 2,
        'max_width_bars': 4,
        'candle_width_days': 90,
    },
    'Y': {
        'freq': 'YE',       # Year End
        'label': '年線',
        'zigzag_threshold': 0.20,
        'min_width_bars': 1,
        'max_width_bars': 3,
        'candle_width_days': 180,
    },
}


def resample_ohlcv(df: pd.DataFrame, timeframe: TimeFrame) -> pd.DataFrame:
    """
    重採樣 OHLCV 數據至指定時間框架

    Args:
        df: 日線 OHLCV DataFrame，必須包含 date, open, high, low, close, volume
        timeframe: 目標時間框架

    Returns:
        重採樣後的 DataFrame（含 date, open, high, low, close, volume）
    """
    if timeframe not in TIMEFRAME_CONFIG:
        raise ValueError(
            f"不支援的時間框架: {timeframe}，"
            f"請使用 {list(TIMEFRAME_CONFIG.keys())}"
        )

    if timeframe == 'D':
        return df.copy().reset_index(drop=True)

    config = TIMEFRAME_CONFIG[timeframe]
    df_work = df.copy()
    df_work['date'] = pd.to_datetime(df_work['date'])
    df_work = df_work.set_index('date').sort_index()

    # 只聚合實際存在的欄位
    agg_rules = {}
    for col, func in [('open', 'first'), ('high', 'max'),
                       ('low', 'min'), ('close', 'last'), ('volume', 'sum')]:
        if col in df_work.columns:
            agg_rules[col] = func

    resampled = (
        df_work
        .resample(config['freq'])
        .agg(agg_rules)
        .dropna(subset=['close'])
        .reset_index()
    )

    return resampled


def get_timeframe_label(timeframe: TimeFrame) -> str:
    """獲取時間框架的中文標籤"""
    return TIMEFRAME_CONFIG.get(timeframe, {}).get('label', timeframe)


def get_zigzag_threshold(timeframe: TimeFrame) -> float:
    """獲取對應時間框架的 ZigZag 閾值"""
    return TIMEFRAME_CONFIG.get(timeframe, {}).get('zigzag_threshold', 0.05)


def get_pattern_width_params(timeframe: TimeFrame) -> Tuple[int, int]:
    """
    獲取形態寬度參數（最小/最大 bar 數）

    Returns:
        (min_width_bars, max_width_bars)
    """
    config = TIMEFRAME_CONFIG.get(timeframe, {})
    return config.get('min_width_bars', 10), config.get('max_width_bars', 60)


def get_candle_width_days(timeframe: TimeFrame) -> float:
    """獲取蠟燭圖柱寬（天數，用於 matplotlib 繪圖）"""
    return TIMEFRAME_CONFIG.get(timeframe, {}).get('candle_width_days', 0.6)
