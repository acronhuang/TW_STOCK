"""計算模組測試"""
import pytest


class TestAdjCloseCalculator:
    def test_import(self):
        from src.calculators.adj_close_calculator import AdjustedCloseCalculator
        calc = AdjustedCloseCalculator()
        assert calc is not None
