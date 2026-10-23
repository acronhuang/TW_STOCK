"""TDD: ATR 與部位算術——手算對照，缺值不猜。"""

import pytest

from src.analysis import atr_sizing as a

pytestmark = pytest.mark.unit

HIGHS = [10.5, 11.5, 12.5, 12.0, 13.5]
LOWS = [9.5, 10.5, 11.5, 10.5, 12.5]
CLOSES = [10, 11, 12, 11, 13]


def test_true_range_first_bar_uses_high_low_only_then_takes_the_largest_gap():
    assert a.true_ranges(HIGHS, LOWS, CLOSES) == [1.0, 1.5, 1.5, 1.5, 2.5]


def test_atr_matches_hand_calculation():
    # 起點 (1.5+1.5+1.5)/3 = 1.5；再 (2×1.5 + 2.5)/3
    assert a.atr(HIGHS, LOWS, CLOSES, period=3) == pytest.approx(5.5 / 3)


def test_atr_needs_period_plus_one_bars():
    assert a.atr(HIGHS[:3], LOWS[:3], CLOSES[:3], period=3) is None
    assert a.atr(HIGHS[:4], LOWS[:4], CLOSES[:4], period=3) == pytest.approx(1.5)


@pytest.mark.parametrize("bad", [None, 0, -1, float("nan"), True, "10"])
def test_atr_refuses_to_guess_when_any_value_is_missing_or_invalid(bad):
    closes = list(CLOSES)
    closes[2] = bad
    assert a.atr(HIGHS, LOWS, closes, period=3) is None


def test_atr_rejects_high_below_low_and_ragged_inputs():
    assert a.atr([9.0] + HIGHS[1:], LOWS, CLOSES, period=3) is None
    assert a.atr(HIGHS[:-1], LOWS, CLOSES, period=3) is None


def test_stop_is_entry_minus_two_n_and_none_when_it_would_not_be_positive():
    assert a.stop_price(100, 5) == 90
    assert a.stop_price(100, 5, mult=3) == 85
    assert a.stop_price(10, 6) is None
    assert a.stop_price(None, 5) is None


def test_add_levels_step_half_n_each():
    assert a.add_levels(100, 4, count=3) == [102, 104, 106]
    assert a.add_levels(100, 0) == []


def test_position_pct_formula():
    # N 占股價 2%、停損 2N=4%，單筆風險 1% 資金 → 部位 25% 資金
    assert a.position_pct(2.0, risk_pct=1.0) == pytest.approx(25.0)
    assert a.position_pct(2.0, risk_pct=2.0) == pytest.approx(50.0)
    assert a.position_pct(0) is None


def test_shares_for_risk_rounds_down_to_lots():
    # 資金 100 萬、風險 1% = 1 萬元；進場 100、停損 90 → 每股虧 10 → 1000 股
    assert a.shares_for_risk(1_000_000, 100, 90, 1.0) == 1000
    assert a.shares_for_risk(1_000_000, 100, 94, 1.0) == 1000  # 原 1666 股向下取整到一張
    assert a.shares_for_risk(1_000_000, 100, 94, 1.0, lot=1) == 1666


def test_shares_for_risk_none_when_stop_not_below_entry_or_bad_input():
    assert a.shares_for_risk(1_000_000, 100, 100) is None
    assert a.shares_for_risk(1_000_000, 100, 110) is None
    assert a.shares_for_risk(0, 100, 90) is None


def test_summary_converts_n_from_adjusted_to_current_price_units():
    adjusted = [c * 0.5 for c in CLOSES]
    result = a.summary([h * 0.5 for h in HIGHS], [l * 0.5 for l in LOWS], adjusted, price=26.0, period=3)
    # 還原序列是現價的一半：N 還原 = 5.5/6，換回現價 = ×(26/6.5)
    assert result["n"] == pytest.approx(round(5.5 / 6 * 26 / 6.5, 2))
    assert result["stop_2n"] == pytest.approx(round(26 - 2 * 5.5 / 6 * 26 / 6.5, 2))
    assert result["n_pct"] == pytest.approx(round(5.5 / 6 * 26 / 6.5 / 26 * 100, 2))


def test_summary_none_without_enough_data_or_price():
    assert a.summary(HIGHS[:2], LOWS[:2], CLOSES[:2], price=13) is None
    assert a.summary(HIGHS, LOWS, CLOSES, price=None, period=3) is None


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, projection):
        self.query = query
        return self

    def sort(self, key, direction):
        return self

    def limit(self, n):
        return self.rows[:n]


def _analyzer(rows):
    from src.analysis.risk_manager import RiskAnalyzer
    from src.domain.collections import COLL_STOCK_PRICE

    analyzer = RiskAnalyzer.__new__(RiskAnalyzer)
    analyzer.db = {COLL_STOCK_PRICE: FakeCollection(rows)}
    return analyzer


def _bars(count, close=100.0, spread=1.0):
    return [{"adj_high": close + spread, "adj_low": close - spread, "adj_close": close} for _ in range(count)]


def test_analyzer_atr_summary_from_stored_bars():
    result = _analyzer(_bars(30))._atr_summary("2330", 100.0)

    assert result["n"] == 2.0 and result["n_pct"] == 2.0 and result["stop_2n"] == 96.0
    assert result["position_pct"] == 25.0  # 1% ÷ (2 × 2%)


def test_analyzer_atr_summary_rescales_when_price_differs_from_adjusted_close():
    assert _analyzer(_bars(30))._atr_summary("2330", 200.0)["n"] == 4.0


def test_analyzer_atr_summary_is_none_when_a_bar_is_missing_a_field():
    rows = _bars(30)
    rows[10]["adj_high"] = None
    assert _analyzer(rows)._atr_summary("2330", 100.0) is None


def test_analyzer_atr_summary_is_none_with_too_few_bars():
    assert _analyzer(_bars(10))._atr_summary("2330", 100.0) is None


def test_analyzer_atr_summary_reads_bars_oldest_to_newest_even_though_the_db_returns_newest_first():
    asc = _bars(25, close=50.0) + _bars(10, close=100.0)  # 舊的在前：先 50 元、後 100 元
    highs, lows, closes = ([bar[k] for bar in asc] for k in ("adj_high", "adj_low", "adj_close"))
    expected = a.summary(highs, lows, closes, 100.0)

    assert expected["n"] > 2.0  # 兩段價位之間的跳空讓 ATR 大於平盤時的 2
    assert _analyzer(asc[::-1])._atr_summary("2330", 100.0) == expected
