"""TDD: 訊號驗證的統計工具——手算對照，缺價不當 0，判定規則事前固定。"""

import numpy as np
import pytest
from scipy import stats

from src.analysis import signal_study as ss

pytestmark = pytest.mark.unit

NAN = np.nan


def test_excess_is_stock_return_minus_the_equal_weight_market():
    close = np.array([[100.0, 100.0, 100.0], [110.0, 100.0, 100.0]])
    excess, market = ss.build_excess(close, min_stocks=2)
    assert np.isnan(market[0]) and market[1] == pytest.approx(0.10 / 3)
    assert excess[1] == pytest.approx([0.10 - 0.10 / 3, -0.10 / 3, -0.10 / 3])
    assert np.all(np.isnan(excess[0]))


def test_a_return_beyond_the_limit_is_a_data_error_and_leaves_the_market_mean():
    close = np.array([[100.0, 100.0, 100.0], [140.0, 105.0, 95.0]])
    excess, market = ss.build_excess(close, min_stocks=2)
    assert np.isnan(excess[1, 0]) and market[1] == pytest.approx(0.0)  # +40% 被丟掉，剩 +5% 與 −5%


def test_a_return_between_the_index_jump_and_the_data_error_limit_stays_in_the_stock_but_not_the_market():
    close = np.array([[100.0, 100.0, 100.0], [113.0, 105.0, 95.0]])
    excess, market = ss.build_excess(close, min_stocks=2)
    assert market[1] == pytest.approx(0.0) and excess[1, 0] == pytest.approx(0.13)


def test_the_market_is_missing_when_too_few_stocks_have_prices():
    close = np.array([[100.0, NAN, NAN], [110.0, NAN, NAN]])
    excess, market = ss.build_excess(close, min_stocks=2)
    assert np.isnan(market[1]) and np.all(np.isnan(excess[1]))


def test_a_missing_price_makes_the_stock_excess_missing_not_zero():
    close = np.array([[100.0, 100.0, 100.0], [101.0, NAN, 99.0], [102.0, 100.0, 98.0]])
    excess, _ = ss.build_excess(close, min_stocks=2)
    assert np.isnan(excess[1, 1]) and np.isnan(excess[2, 1])  # 前後兩天的報酬都算不出來


EXCESS = np.array([[NAN], [0.01], [0.02], [0.03], [NAN], [0.05]])


@pytest.mark.parametrize("row, start, end, expected", [
    (1, 1, 2, 0.05),       # 第 2、3 列：0.02 + 0.03
    (1, 1, 3, None),       # 窗口含缺值
    (4, 1, 3, None),       # 超出最後一列
    (0, 0, 1, None),       # 第 0 列沒有報酬
    (2, 0, 1, 0.05),
    (0, 1, 1, 0.01),       # 第 1 列是第一個有報酬的列，仍算在範圍內
    (4, 1, 2, None),       # 窗口最後一天剛好超出資料範圍
])
def test_window_sums(row, start, end, expected):
    got = ss.Windows(EXCESS).sums(np.array([row]), np.array([0]), start, end)[0]
    assert np.isnan(got) if expected is None else got == pytest.approx(expected)


def test_a_window_that_ends_exactly_on_the_last_row_is_inside_the_data():
    excess = np.array([[NAN], [0.01], [0.02]])
    assert ss.Windows(excess).sums(np.array([0]), np.array([0]), 1, 2)[0] == pytest.approx(0.03)


def test_dedupe_keeps_the_first_event_of_each_stock_within_the_gap():
    rows, cols = ss.dedupe(np.array([30, 10, 5, 7]), np.array([0, 0, 0, 1]), gap=20)
    assert sorted(zip(rows.tolist(), cols.tolist())) == [(5, 0), (7, 1), (30, 0)]  # 10 距 5 只有 5 天；30 距 5 有 25 天


def test_dedupe_gap_boundary_is_exclusive():
    rows, cols = ss.dedupe(np.array([5, 25, 26]), np.array([0, 0, 0]), gap=20)
    assert rows.tolist() == [5, 26]  # 25 距 5 剛好 20 天仍算重複；26 距 5 有 21 天


def test_day_means_average_same_day_events_first_and_skip_missing():
    days, means = ss.day_means(np.array([1, 1, 2, 3, 3, 3]), np.array([1.0, 3.0, 5.0, 2.0, 4.0, NAN]))
    assert days.tolist() == [1, 2, 3] and means.tolist() == [2.0, 5.0, 3.0]


def test_t_summary_matches_the_textbook_formula_and_refuses_degenerate_input():
    got = ss.t_summary([1, 2, 3, 4, 5])
    assert got["mean"] == 3 and got["t"] == pytest.approx(3 / (np.std([1, 2, 3, 4, 5], ddof=1) / np.sqrt(5)))
    assert got["p"] == pytest.approx(2 * stats.t.sf(4.242640687, 4))
    assert np.isnan(ss.t_summary([1.0])["t"]) and np.isnan(ss.t_summary([2.0, 2.0, 2.0])["t"])


def test_versus_baseline_compares_on_the_same_days_only():
    got = ss.versus_baseline(np.array([1, 1, 2, 4]), np.array([0.02, 0.04, 0.01, 0.9]),
                             np.array([1, 2, 3]), np.array([0.01, 0.01, 0.5]))
    # 第 1 天 0.03−0.01、第 2 天 0.01−0.01；第 4 天沒有基準，不納入
    assert got["days"] == 2 and got["mean"] == pytest.approx(0.01) and got["t"] == pytest.approx(1.0)


def test_group_gap_is_a_paired_difference_on_shared_days():
    got = ss.group_gap(np.array([1, 2, 5]), np.array([0.0, -0.02, 9.0]), np.array([1, 2, 3]), np.array([0.03, 0.03, 0.0]))
    assert got["days"] == 2 and got["mean"] == pytest.approx(-0.04)


def test_benjamini_hochberg_classic_example_and_order_preserved():
    p = [0.216, 0.001, 0.205, 0.008, 0.039, 0.041, 0.042, 0.060, 0.074, 0.212]
    got = ss.benjamini_hochberg(p, q=0.05)
    assert [i for i, ok in enumerate(got) if ok] == [1, 3]


def test_benjamini_hochberg_treats_nan_as_not_significant_and_handles_none_passing():
    assert ss.benjamini_hochberg([float("nan"), 0.2, 0.9], q=0.1).tolist() == [False, False, False]
    assert ss.benjamini_hochberg([0.001, float("nan")], q=0.1).tolist() == [True, False]


def test_benjamini_hochberg_threshold_is_inclusive():
    assert ss.benjamini_hochberg([0.05], q=0.05).tolist() == [True]


GOOD = {"days": 100, "events": 500, "mean": 0.01}


def test_decide_supported_needs_both_periods_in_the_hypothesised_direction_and_fdr():
    assert ss.decide(GOOD, GOOD, +1, True) == ss.SUPPORTED
    assert ss.decide({**GOOD, "mean": -0.01}, {**GOOD, "mean": -0.02}, -1, True) == ss.SUPPORTED


@pytest.mark.parametrize("dev, hold, direction, significant", [
    (GOOD, GOOD, +1, False),                                  # 留存期沒通過 FDR
    ({**GOOD, "mean": -0.01}, GOOD, +1, True),                # 開發期方向相反
    (GOOD, {**GOOD, "mean": -0.01}, +1, True),                # 留存期方向相反
    (GOOD, GOOD, -1, True),                                   # 假設為負但兩期都為正
])
def test_decide_not_supported(dev, hold, direction, significant):
    assert ss.decide(dev, hold, direction, significant) == ss.NOT_SUPPORTED


@pytest.mark.parametrize("override", [{"days": 59}, {"events": 299}, {"mean": float("nan")}])
def test_decide_insufficient_sample_in_either_period(override):
    assert ss.decide({**GOOD, **override}, GOOD, +1, True) == ss.INSUFFICIENT
    assert ss.decide(GOOD, {**GOOD, **override}, +1, True) == ss.INSUFFICIENT


def test_decide_boundary_samples_are_enough():
    assert ss.decide({"days": 60, "events": 300, "mean": 0.01}, GOOD, +1, True) == ss.SUPPORTED
