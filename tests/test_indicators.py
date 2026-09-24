"""技術指標模組測試"""
import pytest
import pandas as pd
import numpy as np

# 分層修正(2026-09-25):原模組一律標 integration,但 MA/MACD 是純 pandas/numpy
# 運算、零 DB → 改標 unit 納入免-DB 秒級閘門(還運算回歸安全網)。
# 僅 test_rsi_range 真從 db 讀 2330 價格 → 保留 integration。


class TestRSI:
    @pytest.mark.integration
    @pytest.mark.needs_data
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
    @pytest.mark.unit
    def test_ma_calculation(self):
        from src.indicators.ma import calculate_ma
        data = pd.Series([10, 11, 12, 13, 14, 15])
        ma3 = calculate_ma(data, periods=[3])
        assert len(ma3) > 0


class TestMACD:
    @pytest.mark.unit
    def test_macd_output(self):
        from src.indicators.macd import calculate_macd
        data = pd.Series(np.random.random(50) * 100 + 100)
        result = calculate_macd(data)
        assert result is not None
