"""
蔡森形態學模組 (Morphology Pattern Recognition)

此模組實現蔡森老師的技術形態學，作為量化選股的「二次過濾器」。

核心形態：
- 破底翻 (Bottom Reversal)
- 雙底 (W Bottom)
- 頸線突破 (Neckline Breakout)
- 量價噴出 (Volume Surge)
- 量價背離 (Volume-Price Divergence)

作者: Ming
版本: v2.1.0
創建日期: 2026-02-23
"""

from .pattern_detector import PatternDetector
from .bottom_reversal import detect_bottom_reversal
from .w_bottom import detect_w_bottom
from .neckline_breakout import detect_neckline_breakout
from .volume_analysis import detect_volume_surge, detect_volume_price_divergence
from .pattern_scorer import calculate_pattern_strength, PatternScorer

__version__ = "2.1.0"
__author__ = "Ming"

__all__ = [
    "PatternDetector",
    "detect_bottom_reversal",
    "detect_w_bottom",
    "detect_neckline_breakout",
    "detect_volume_surge",
    "detect_volume_price_divergence",
    "calculate_pattern_strength",
    "PatternScorer",
]
