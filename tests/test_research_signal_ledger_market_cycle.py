"""TDD: 北大市場週期對加權指數的擇時評估（純函式，無任何寫入）。"""

from datetime import date, timedelta

import pytest

from src.research_signal_ledger.market_cycle import (
    CycleCall,
    cycle_exposure,
    evaluate_cycle_timing,
)


pytestmark = pytest.mark.unit


def calls(*pairs):
    start = date(2026, 1, 5)
    return [CycleCall(start + timedelta(days=i), cycle) for i, cycle in enumerate(pairs)]


def index(*closes):
    start = date(2026, 1, 5)
    return {start + timedelta(days=i + 1): close for i, close in enumerate(closes)}


def test_each_cycle_maps_to_the_midpoint_of_its_suggested_position():
    assert cycle_exposure("spring") == pytest.approx(0.25)
    assert cycle_exposure("summer") == pytest.approx(0.60)
    assert cycle_exposure("autumn") == pytest.approx(0.25)
    assert cycle_exposure("winter") == pytest.approx(0.05)


def test_an_unknown_cycle_has_no_exposure_and_is_skipped():
    assert cycle_exposure("monsoon") is None
    assert cycle_exposure(None) is None


def test_a_rising_market_rewards_the_high_exposure_cycle_less_than_buy_and_hold():
    result = evaluate_cycle_timing(calls("summer", "summer"), index(100.0, 110.0, 121.0), horizon=1)

    assert result["samples"] == 2
    assert result["mean_buy_hold_pct"] == pytest.approx(10.0)
    assert result["mean_timed_pct"] == pytest.approx(6.0)
    assert result["mean_edge_pct"] == pytest.approx(-4.0)


def test_a_falling_market_rewards_the_low_exposure_cycle():
    result = evaluate_cycle_timing(calls("winter", "winter"), index(100.0, 90.0, 81.0), horizon=1)

    assert result["mean_buy_hold_pct"] == pytest.approx(-10.0)
    assert result["mean_timed_pct"] == pytest.approx(-0.5)
    assert result["mean_edge_pct"] == pytest.approx(9.5)


def test_results_are_reported_per_cycle_so_a_thin_phase_cannot_hide():
    result = evaluate_cycle_timing(
        calls("summer", "summer", "winter"), index(100.0, 110.0, 121.0, 100.0), horizon=1
    )

    assert result["by_cycle"]["summer"]["samples"] == 2
    assert result["by_cycle"]["winter"]["samples"] == 1


def test_a_cycle_with_too_few_calls_is_flagged_as_inconclusive():
    result = evaluate_cycle_timing(calls("winter", "summer", "summer"), index(100.0, 90.0, 99.0, 108.9), horizon=1)

    assert result["by_cycle"]["winter"]["conclusive"] is False


def test_changing_the_cycle_costs_a_round_trip_on_the_exposure_change_only():
    steady = evaluate_cycle_timing(calls("summer", "summer"), index(100.0, 100.0, 100.0), horizon=1)
    switching = evaluate_cycle_timing(calls("summer", "winter"), index(100.0, 100.0, 100.0), horizon=1)

    assert steady["mean_timed_pct"] == pytest.approx(0.0)
    assert switching["mean_timed_pct"] < 0.0


def test_calls_without_a_future_index_price_are_dropped_not_zero_filled():
    result = evaluate_cycle_timing(calls("summer", "summer", "summer"), index(100.0, 110.0), horizon=1)

    assert result["samples"] == 1


def test_no_calls_report_no_samples():
    result = evaluate_cycle_timing([], index(100.0, 110.0), horizon=1)

    assert result["samples"] == 0
    assert result["mean_edge_pct"] is None
