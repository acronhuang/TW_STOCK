"""
SenVision 量化形態選股系統

基於蔡森形態學理論的台股技術分析工具

Modules:
    - zigzag: ZigZag 轉折點提取
    - pattern_detector: 形態識別引擎（W底/M頭/三重底/三重頂）
    - scanner: 市場掃描器
    - multi_timeframe: 日/週/月/季/半年/年多時間框架重採樣
    - support_resistance: 支撐壓力強度評估
    - trendline: 趨勢切線自動識別（破切）
    - chart_visualizer: 完整技術分析圖表引擎

Author: SenVision Team
Version: 0.2.0
Date: 2026-02-24
"""

__version__ = '0.2.0'
__author__ = 'SenVision Team'

from .analysis import analyze_timeframe, get_ma_alignment, score_signal
from .chart_visualizer import SenVisionChart
from .multi_timeframe import (
    TIMEFRAME_CONFIG,
    get_candle_width_days,
    get_pattern_width_params,
    get_timeframe_label,
    get_zigzag_threshold,
    resample_ohlcv,
)
from .pattern_bridge import detect_12masters_patterns
from .pattern_detector import (
    MTopDetector,
    Pattern,
    PatternDetector,
    PatternStatus,
    PatternType,
    TripleBottomDetector,
    TripleTopDetector,
    WBottomDetector,
)
from .scanner import MarketScanner
from .support_resistance import SRLevel, find_support_resistance
from .trendline import (
    Trendline,
    detect_trendline_break,
    find_ascending_support,
    find_descending_resistance,
)
from .zigzag import Peak, ZigZagIndicator, plot_zigzag

__all__ = [
    # ZigZag
    'ZigZagIndicator',
    'Peak',
    'plot_zigzag',

    # Pattern Detection
    'Pattern',
    'PatternType',
    'PatternStatus',
    'PatternDetector',
    'WBottomDetector',
    'MTopDetector',
    'TripleBottomDetector',
    'TripleTopDetector',

    # Scanner
    'MarketScanner',

    # Multi-Timeframe
    'resample_ohlcv',
    'get_timeframe_label',
    'get_zigzag_threshold',
    'get_pattern_width_params',
    'get_candle_width_days',
    'TIMEFRAME_CONFIG',

    # Support & Resistance
    'SRLevel',
    'find_support_resistance',

    # Trendline
    'Trendline',
    'find_descending_resistance',
    'find_ascending_support',
    'detect_trendline_break',

    # Chart
    'SenVisionChart',

    # Analysis Engine
    'analyze_timeframe',
    'score_signal',
    'get_ma_alignment',

    # Pattern Bridge (12 神招)
    'detect_12masters_patterns',
]
