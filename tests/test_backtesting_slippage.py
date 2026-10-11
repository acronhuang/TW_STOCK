"""TDD: 回測滑價只改變成交價，且必須明確驗證輸入。"""

import pytest

from src.backtesting.slippage import execution_price


pytestmark = pytest.mark.unit


def test_execution_price_moves_against_the_trade_direction():
    assert execution_price(100, "buy", 10) == pytest.approx(100.1)
    assert execution_price(100, "sell", 10) == pytest.approx(99.9)
    assert execution_price(100, "buy") == pytest.approx(100)


@pytest.mark.parametrize(
    ("market_price", "side", "slippage_bps"),
    [(0, "buy", 0), (100, "hold", 0), (100, "buy", -1)],
)
def test_execution_price_rejects_invalid_inputs(market_price, side, slippage_bps):
    with pytest.raises(ValueError):
        execution_price(market_price, side, slippage_bps)