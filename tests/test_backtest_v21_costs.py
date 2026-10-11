"""TDD: v21 每日出場必須與再平衡出場使用相同的台股成本。"""

from types import SimpleNamespace

import pytest

from scripts.backtest_integrated_v21 import BacktestV21


pytestmark = pytest.mark.unit


class FakeExitStrategy:
    def check_exit_signals(self, _holdings, _date):
        return [
            SimpleNamespace(
                should_exit=True,
                stock_id="2330",
                current_price=100.0,
                return_pct=0.0,
                exit_reason="stop_loss",
            )
        ]


def test_daily_exit_applies_fee_tax_and_preserves_exit_reason():
    backtester = BacktestV21.__new__(BacktestV21)
    backtester.strategy_v21 = FakeExitStrategy()
    backtester.positions = {
        "2330": {"shares": 1_000, "entry_price": 100.0, "entry_date": "2026-10-01"}
    }
    backtester.capital = 0.0
    backtester.fee_rate = 0.001425
    backtester.fee_discount = 0.6
    backtester.tax_rate = 0.003
    backtester.min_fee = 20.0
    backtester.slippage_bps = 0.0
    backtester.total_fees = 0.0
    backtester.total_taxes = 0.0
    backtester.trades = []

    backtester.check_daily_exits("2026-10-09")

    assert backtester.capital == pytest.approx(99_614.5)
    assert backtester.total_fees == pytest.approx(85.5)
    assert backtester.total_taxes == pytest.approx(300.0)
    assert backtester.trades[0]["exit_reason"] == "stop_loss"
    assert "2330" not in backtester.positions


def test_daily_exit_applies_slippage_before_fee_and_tax():
    backtester = BacktestV21.__new__(BacktestV21)
    backtester.strategy_v21 = FakeExitStrategy()
    backtester.positions = {
        "2330": {"shares": 1_000, "entry_price": 100.0, "entry_date": "2026-10-01"}
    }
    backtester.capital = 0.0
    backtester.fee_rate = 0.001425
    backtester.fee_discount = 0.6
    backtester.tax_rate = 0.003
    backtester.min_fee = 20.0
    backtester.slippage_bps = 10.0
    backtester.total_fees = 0.0
    backtester.total_taxes = 0.0
    backtester.trades = []

    backtester.check_daily_exits("2026-10-09")

    assert backtester.trades[0]["price"] == pytest.approx(99.9)
    assert backtester.capital == pytest.approx(99_514.8855)