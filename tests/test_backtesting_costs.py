"""TDD: 舊回測 Portfolio 必須套用正確的台股買賣成本。"""

from datetime import datetime

import pytest

from src.backtesting.portfolio import Portfolio


pytestmark = pytest.mark.unit


def test_portfolio_applies_asymmetric_taiwan_transaction_costs():
    portfolio = Portfolio(initial_cash=101_000)
    trade_date = datetime(2026, 10, 9)

    assert portfolio.buy(trade_date, "2330", shares=1_000, price=100)

    position = portfolio.get_position("2330")
    assert portfolio.trades[0].commission == pytest.approx(142.5)
    assert position.avg_price == pytest.approx(100.1425)

    assert portfolio.sell(trade_date, "2330", shares=1_000, price=100)

    assert portfolio.trades[1].commission == pytest.approx(442.5)
    assert portfolio.cash == pytest.approx(100_415)


def test_portfolio_applies_slippage_before_taiwan_costs():
    portfolio = Portfolio(initial_cash=101_500, slippage_bps=10)
    trade_date = datetime(2026, 10, 9)

    assert portfolio.buy(trade_date, "2330", shares=1_000, price=100)

    assert portfolio.trades[0].price == pytest.approx(100.1)
    assert portfolio.get_position("2330").avg_price == pytest.approx(100.2426425)