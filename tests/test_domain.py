"""DDD Domain Layer 測試"""
import pytest
from datetime import datetime


class TestStockModel:
    def test_stock_creation(self):
        from src.domain.models.stock import Stock
        s = Stock(symbol='2330', name='台積電', industry='半導體')
        assert s.symbol == '2330'
        assert s.name == '台積電'

    def test_stock_immutable(self):
        from src.domain.models.stock import Stock
        s = Stock(symbol='2330')
        with pytest.raises(AttributeError):
            s.symbol = '9999'

    def test_stock_price_change_pct(self):
        from src.domain.models.stock import StockPrice
        sp = StockPrice(symbol='2330', date=datetime.now(),
                        open=100, high=110, low=95, close=105, volume=1000)
        assert sp.change_pct == pytest.approx(5.0, abs=0.01)

    def test_stock_factor(self):
        from src.domain.models.stock import StockFactor
        sf = StockFactor(symbol='2330', date=datetime.now(),
                         pe_ratio=30, pb_ratio=9.5, dividend_yield=1.1)
        assert sf.pe_ratio == 30


class TestPositionModel:
    def test_position_cost(self):
        from src.domain.models.portfolio import Position
        p = Position(symbol='2330', shares=1000, avg_cost=900)
        assert p.total_cost == 900_000

    def test_unrealized_pnl(self):
        from src.domain.models.portfolio import Position
        p = Position(symbol='2330', shares=1000, avg_cost=100)
        assert p.unrealized_pnl(110) == 10_000
        assert p.unrealized_pnl_pct(110) == pytest.approx(10.0, abs=0.01)

    def test_trade_creation(self):
        from src.domain.models.portfolio import Trade
        t = Trade(symbol='2330', action='BUY', shares=1000,
                  price=900, date=datetime.now())
        assert t.action == 'BUY'


class TestValuationResult:
    def test_undervalued(self):
        from src.domain.models.valuation import ValuationResult
        v = ValuationResult(symbol='2330', current_price=900,
                            composite_fair_value=1200, upside_pct=33.3)
        assert v.is_undervalued is True
        assert v.is_overvalued is False

    def test_overvalued(self):
        from src.domain.models.valuation import ValuationResult
        v = ValuationResult(symbol='2330', current_price=900,
                            composite_fair_value=700, upside_pct=-22.2)
        assert v.is_overvalued is True


class TestStockRepository:
    def test_abstract_interface(self):
        from src.domain.repositories.stock_repository import StockRepository
        with pytest.raises(TypeError):
            StockRepository()  # 不能直接實例化 ABC
