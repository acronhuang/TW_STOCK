"""TDD: 風險暴露調整的統計工具——手算對照，缺資料不猜。"""

import numpy as np
import pytest

from src.analysis import exposure_adjust as ed

pytestmark = pytest.mark.unit


def test_winsorize_clips_both_tails_and_zscore_refuses_a_constant():
    x = np.arange(101, dtype=float)
    clipped = ed.winsorize(x, 0.01)
    assert clipped.min() == pytest.approx(1.0) and clipped.max() == pytest.approx(99.0)
    assert ed.zscore(np.array([3.0, 3.0, 3.0])) is None
    z = ed.zscore(np.array([1.0, 2.0, 3.0]))
    assert z.mean() == pytest.approx(0) and z.std() == pytest.approx(1)


def panel(seed=0, n=300, events=10):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 2))
    d = np.zeros(n)
    d[:events] = 1
    return rng, X, d


def test_the_event_coefficient_is_recovered_exactly_when_y_is_linear():
    _, X, d = panel()
    y = 1.0 + 0.5 * X[:, 0] - 0.3 * X[:, 1] + 0.02 * d
    assert ed.date_gamma(y, X, d, winsor=0) == pytest.approx(0.02)


def test_controlling_for_an_exposure_removes_the_confounded_part():
    rng, X, d = panel(seed=1, n=400, events=40)
    X[:40, 0] += 2.0                                         # 事件個股的暴露比較高
    y = 0.5 * X[:, 0] + rng.normal(0, 0.001, 400)            # 報酬只由暴露決定，沒有真正的事件效果
    assert ed.date_gamma(y, np.empty((400, 0)), d) > 0.5     # 不控制：看起來有效果
    assert abs(ed.date_gamma(y, X, d, winsor=0)) < 0.01      # 控制後消失


def test_winsorizing_limits_the_influence_of_an_outlier_exposure():
    _, X, d = panel(seed=2, n=500, events=20)
    X[:20, 0] += 1.0                                         # 事件個股的暫露較高，所以斜率估錯會污染事件係數
    y = 0.5 * X[:, 0] + 0.02 * d
    X[250, 0] = 1000.0                                       # 這格的暫露是錯誤值，y 並未跟著變
    assert abs(ed.date_gamma(y, X, d, winsor=0.01) - 0.02) < 0.05 < abs(ed.date_gamma(y, X, d, winsor=0) - 0.02)


@pytest.mark.parametrize("make", [
    lambda: (np.zeros(5), np.zeros((5, 1)), np.zeros(5)),                                    # 沒有事件
    lambda: (np.arange(20.0), np.random.default_rng(0).normal(size=(20, 1)), np.r_[1.0, np.zeros(19)]),   # 控制組太少
    lambda: (np.arange(200.0), np.ones((200, 1)), np.r_[np.ones(5), np.zeros(195)]),                      # 暴露無變異
])
def test_date_gamma_refuses_to_guess(make):
    y, X, d = make()
    assert ed.date_gamma(y, X, d) is None


def test_collinear_exposures_are_refused():
    rng, X, d = panel(seed=4)
    X[:, 1] = 2 * X[:, 0]
    assert ed.date_gamma(rng.normal(size=300), X, d) is None


def test_the_minimum_number_of_controls_is_an_inclusive_boundary():
    rng = np.random.default_rng(5)
    for controls, expected_none in ((99, True), (100, False)):
        n = controls + 5
        d = np.r_[np.ones(5), np.zeros(controls)]
        assert (ed.date_gamma(rng.normal(size=n), rng.normal(size=(n, 1)), d) is None) is expected_none


def test_newey_west_with_lag_zero_is_the_plain_t_of_the_mean():
    values = np.array([1.0, 3.0, 2.0, 4.0, 5.0])
    mean, t = ed.newey_west_mean_t(np.arange(5), values, lag=0)
    assert mean == 3.0 and t == pytest.approx(3.0 / (np.sqrt(np.sum((values - 3.0) ** 2)) / 5))


def test_positive_autocorrelation_widens_the_error_and_negative_narrows_it():
    slow = np.sin(np.linspace(0, 3, 60)) + 1
    alternating = np.where(np.arange(60) % 2 == 0, 1.0, 2.0)
    assert abs(ed.newey_west_mean_t(np.arange(60), slow, lag=5)[1]) < abs(ed.newey_west_mean_t(np.arange(60), slow, lag=0)[1])
    assert abs(ed.newey_west_mean_t(np.arange(60), alternating, lag=5)[1]) > abs(ed.newey_west_mean_t(np.arange(60), alternating, lag=0)[1])


def test_missing_dates_count_as_zero_deviation_and_the_bartlett_weight_is_applied():
    # 日期 0 與 2、值 1 與 3：偏差 [−1, 0, +1]；落後 2 日的權重 1−2/3
    mean, t = ed.newey_west_mean_t([0, 2], [1.0, 3.0], lag=2)
    assert mean == 2.0 and t == pytest.approx(2.0 / np.sqrt((2 + 2 * (1 - 2 / 3) * -1) / 4))


def test_newey_west_needs_two_dates_and_some_variation():
    assert all(np.isnan(v) for v in ed.newey_west_mean_t([3], [0.1]))
    assert np.isnan(ed.newey_west_mean_t([0, 1, 2], [0.5, 0.5, 0.5])[1])


def test_exposures_match_hand_calculation():
    days = 200
    rng = np.random.default_rng(7)
    market = rng.normal(0.0, 0.01, days)
    ret = np.column_stack([2 * market, -0.5 * market, np.full(days, 0.01)])
    close = 100 * np.cumprod(1 + np.where(np.isnan(ret), 0, ret), axis=0)
    close = np.column_stack([close[:, 0], close[:, 1], 100 * 1.01 ** np.arange(days)])
    value = np.tile(np.array([1e8, 5e8, 1e9]), (days, 1))
    got = ed.exposures(close, ret, market, value)
    assert got["beta"][150, 0] == pytest.approx(2.0) and got["beta"][150, 1] == pytest.approx(-0.5)
    assert np.isnan(got["beta"][10, 0])                                       # 窗口內資料不足 40 筆
    assert got["vol"][150, 2] == pytest.approx(0.0, abs=1e-12)                # 報酬固定→標準差 0
    assert got["size"][150].tolist() == pytest.approx(np.log([1e8, 5e8, 1e9]).tolist())
    assert got["short"][150, 2] == pytest.approx(1.01 ** 20 - 1)
    assert got["mom"][150, 2] == pytest.approx(1.01 ** 100 - 1)               # t−20 對 t−120，相隔 100 天
    assert np.isnan(got["mom"][100, 2]) and np.isnan(got["short"][10, 2])


def test_exposures_use_only_data_up_to_the_row_itself():
    rng = np.random.default_rng(8)
    days = 220
    market = rng.normal(0, 0.01, days)
    ret = rng.normal(0, 0.02, (days, 3))
    close = 100 * np.cumprod(1 + ret, axis=0)
    value = rng.uniform(1e7, 1e9, (days, 3))
    full = ed.exposures(close, ret, market, value)
    cut = ed.exposures(close[:170], ret[:170], market[:170], value[:170])
    for key in full:
        assert np.allclose(full[key][:170], cut[key], equal_nan=True)


def test_volatility_is_the_sample_standard_deviation_of_the_last_sixty_returns():
    rng = np.random.default_rng(9)
    days = 150
    ret = rng.normal(0, 0.02, (days, 1))
    got = ed.exposures(100 * np.cumprod(1 + ret, axis=0), ret, rng.normal(0, 0.01, days), np.full((days, 1), 1e8))
    assert got["vol"][120, 0] == pytest.approx(np.std(ret[61:121, 0], ddof=1))
