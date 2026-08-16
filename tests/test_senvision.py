"""SenVision 多時間框架分析測試"""
import pytest
import numpy as np

# ADR-0011 分類（2026-08-16）：純演算法
pytestmark = pytest.mark.unit


class TestZigZag:
    def test_import(self):
        from src.senvision.zigzag import ZigZagIndicator
        zz = ZigZagIndicator()
        assert zz is not None


class TestTrendline:
    def test_import(self):
        from src.senvision.trendline import Trendline
        assert Trendline is not None

    def test_find_support(self):
        from src.senvision.trendline import find_ascending_support
        assert callable(find_ascending_support)


class TestSupportResistance:
    def test_import(self):
        from src.senvision.support_resistance import find_support_resistance
        assert callable(find_support_resistance)
