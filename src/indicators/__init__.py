"""
技術指標模組
提供完整的技術分析指標計算功能

包含指標:
- 趨勢指標: MA (移動平均線)
- 動能指標: RSI (相對強弱指標), MACD (移動平均收斂發散指標), KD (隨機指標)
- 通道指標: Bollinger Bands (布林通道)
- 成交量指標: OBV (能量潮指標)
"""

# MA 移動平均線
from .ma import (
    calculate_ma,
    calculate_ema,
    calculate_ma_crossover,
    calculate_ma_support_resistance
)

# RSI 相對強弱指標
from .rsi import (
    calculate_rsi,
    calculate_rsi_signals,
    calculate_rsi_divergence
)

# MACD 移動平均收斂發散指標
from .macd import (
    calculate_macd,
    calculate_macd_signals,
    calculate_macd_divergence
)

# KD 隨機指標
from .kd import (
    calculate_kd,
    calculate_kd_signals,
    calculate_kd_divergence
)

# Bollinger Bands 布林通道
from .bollinger import (
    calculate_bollinger_bands,
    calculate_bollinger_signals,
    calculate_bollinger_squeeze
)

# OBV 能量潮指標
from .obv import (
    calculate_obv,
    calculate_obv_signals,
    calculate_obv_divergence,
    calculate_obv_trend_strength
)

__all__ = [
    # MA 移動平均線
    'calculate_ma',
    'calculate_ema',
    'calculate_ma_crossover',
    'calculate_ma_support_resistance',
    
    # RSI 相對強弱指標
    'calculate_rsi',
    'calculate_rsi_signals',
    'calculate_rsi_divergence',
    
    # MACD 移動平均收斂發散指標
    'calculate_macd',
    'calculate_macd_signals',
    'calculate_macd_divergence',
    
    # KD 隨機指標
    'calculate_kd',
    'calculate_kd_signals',
    'calculate_kd_divergence',
    
    # Bollinger Bands 布林通道
    'calculate_bollinger_bands',
    'calculate_bollinger_signals',
    'calculate_bollinger_squeeze',
    
    # OBV 能量潮指標
    'calculate_obv',
    'calculate_obv_signals',
    'calculate_obv_divergence',
    'calculate_obv_trend_strength',
]

__version__ = '1.0.0'
