"""計算模組測試"""
import pytest

# ADR-0011 分類（2026-08-16）：純計算
pytestmark = pytest.mark.unit


class TestAdjCloseCalculator:
    def test_import(self):
        from src.calculators.adj_close_calculator import AdjustedCloseCalculator
        calc = AdjustedCloseCalculator()
        assert calc is not None
