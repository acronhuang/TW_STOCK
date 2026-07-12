"""型態辨識模組測試"""
import pytest
import numpy as np
import pandas as pd


class TestPatternDetector:
    def test_import(self):
        from src.morphology.pattern_detector import PatternDetector
        pd_ = PatternDetector()
        assert pd_ is not None


class TestPivotPoints:
    def test_detect_pivot_highs(self):
        from src.morphology.pivot_points import detect_pivot_highs
        assert callable(detect_pivot_highs)

    def test_get_pivot_points(self):
        from src.morphology.pivot_points import get_pivot_points
        assert callable(get_pivot_points)


class TestVolumeAnalysis:
    def test_volume_surge(self):
        from src.morphology.volume_analysis import detect_volume_surge
        assert callable(detect_volume_surge)

    def test_volume_surge_basic(self):
        from src.morphology.volume_analysis import detect_volume_surge
        df = pd.DataFrame({
            'open': [10]*20, 'high': [11]*20, 'low': [9]*20,
            'close': [10]*20, 'volume': [100]*19 + [500],
        })
        result = detect_volume_surge(df)
        assert result is not None
