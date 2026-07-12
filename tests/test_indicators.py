"""技術指標模組測試"""
import pytest
import pandas as pd
import numpy as np


class TestRSI:
    def test_rsi_range(self, db):
        from src.indicators.rsi import calculate_rsi
        closes = [float(p['close'].to_decimal()) for p in
                  db.stock_price.find({'symbol': '2330'}, {'close': 1}).sort('date', -1).limit(30)]
        if len(closes) >= 14:
            series = pd.Series(closes[::-1])
            rsi = calculate_rsi(series, period=14)
            last_rsi = rsi.dropna().iloc[-1]
            assert 0 <= last_rsi <= 100


class TestMA:
    def test_ma_calculation(self):
        from src.indicators.ma import calculate_ma
        data = pd.Series([10, 11, 12, 13, 14, 15])
        ma3 = calculate_ma(data, periods=[3])
        assert len(ma3) > 0


class TestMACD:
    def test_macd_output(self):
        from src.indicators.macd import calculate_macd
        data = pd.Series(np.random.random(50) * 100 + 100)
        result = calculate_macd(data)
        assert result is not None
