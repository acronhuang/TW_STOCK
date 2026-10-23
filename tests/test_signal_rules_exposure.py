"""TDD: s_stretch 風險暴露調整——控制組定義、混淆被去除、真效果被留下、判定標準事前固定。"""

import sys

import numpy as np
import pandas as pd
import pytest

from scripts import signal_rules_exposure as xp
from scripts import signal_rules_study as study
from src.analysis import signal_study as ss

pytestmark = pytest.mark.unit


def test_registered_specs_and_criterion():
    assert xp.SPECS == {"無控制": (), "A": ("beta", "vol", "size", "mom"), "B": ("beta", "vol", "size", "mom", "short")}
    assert xp.PRIMARY_RULE == "s_stretch" and xp.SURVIVE_T == 2.0 and xp.ALL == ("beta", "vol", "size", "mom", "short")


def test_controls_exclude_any_cell_with_a_signal_in_the_last_twenty_rows_including_today():
    mask = np.zeros((60, 2), dtype=bool)
    mask[10, 0] = True
    ones = np.ones((60, 2), dtype=bool)
    control = xp.controls_of(mask, ones, ones)
    assert not control[10:30, 0].any() and control[9, 0] and control[30, 0]      # 第 10 列起連續 20 列（10..29）被排除
    assert control[:, 1].all()


def test_controls_need_the_premise_and_the_live_universe():
    mask = np.zeros((30, 1), dtype=bool)
    premise, live = np.ones((30, 1), dtype=bool), np.ones((30, 1), dtype=bool)
    premise[5], live[6] = False, False
    control = xp.controls_of(mask, premise, live)
    assert not control[5, 0] and not control[6, 0] and control[7, 0]


def world(kind, seed=11, days=320, stocks=400):
    rng = np.random.default_rng(seed)
    beta = rng.normal(1, 0.3, stocks)
    expo = {key: np.tile(rng.normal(size=stocks), (days, 1)) for key in xp.ALL}
    expo["beta"] = np.tile(beta, (days, 1))
    factor = rng.normal(0.002, 0.004, days)
    excess = np.full((days, stocks), np.nan)
    excess[1:] = beta * factor[1:, None] + rng.normal(0, 0.01, (days - 1, stocks))
    rate = np.full((days, stocks), 0.02 if kind != "confound" else 0.0)
    if kind == "confound":
        rate = np.clip(0.04 * np.exp(5 * (beta - 1)), 0, 0.5)[None, :].repeat(days, axis=0)
    elif kind == "planted":
        rate = np.full((days, stocks), 0.01)
    mask = rng.random((days, stocks)) < rate
    mask[:30] = False
    mask[-30:] = False
    if kind == "planted":
        for r, c in zip(*np.nonzero(mask)):
            excess[r + 2:r + 22, c] += 0.001                         # 事件後 t+2..t+21 每天多 0.1%，窗口共 +2%
    ones = np.ones((days, stocks), dtype=bool)
    return mask, ones, ones, expo, ss.Windows(excess)


@pytest.fixture(scope="module")
def confounded():
    return xp.analyze(*world("confound"))


@pytest.fixture(scope="module")
def planted():
    return xp.analyze(*world("planted"))


@pytest.fixture(scope="module")
def null():
    return xp.analyze(*world("null"))


def test_a_beta_driven_pseudo_effect_shows_up_without_controls_and_vanishes_with_them(confounded):
    assert confounded["無控制"]["gamma"] > 0.01 and confounded["無控制"]["t"] > 2.5
    assert abs(confounded["A"]["gamma"]) < 0.008 and abs(confounded["A"]["t"]) < 3
    assert confounded["A"]["gamma"] < confounded["無控制"]["gamma"] / 2
    assert not xp.survives(confounded)


def test_a_planted_event_effect_survives_the_controls_and_is_about_the_planted_size(planted):
    assert 0.012 < planted["A"]["gamma"] < 0.035 and planted["A"]["t"] > 3
    assert xp.survives(planted)


def test_no_effect_and_no_confounding_means_no_survival(null):
    assert abs(null["A"]["gamma"]) < 0.008 and not xp.survives(null)


def test_every_spec_uses_the_same_dates_and_events_when_exposures_are_always_present(planted):
    assert len({(v["dates"], v["events"]) for v in planted.values()}) == 1 and planted["A"]["dates"] > 100


def test_cells_missing_any_exposure_are_dropped_from_every_spec():
    mask, premise, live, expo, windows = world("planted", days=200, stocks=300)
    full = xp.analyze(mask, premise, live, expo, windows)
    expo = {**expo, "short": expo["short"].copy()}
    expo["short"][:, :150] = np.nan                                           # 一半個股缺其中一個暴露
    half = xp.analyze(mask, premise, live, expo, windows)
    assert half["A"]["events"] < full["A"]["events"]                          # 連規格 A 也跟著少（共同樣本）
    assert half["A"]["events"] == half["B"]["events"] == half["無控制"]["events"]


def test_survives_requires_a_positive_coefficient_and_t_at_least_two():
    def result(gamma, t):
        return {"A": {"gamma": gamma, "t": t, "dates": 100, "events": 500}}

    assert xp.survives(result(0.01, 2.0)) and not xp.survives(result(0.01, 1.99))
    assert not xp.survives(result(-0.01, 5.0)) and not xp.survives(result(0.0, 5.0))
    assert not xp.survives(result(float("nan"), float("nan")))


def test_render_states_the_criterion_the_verdict_and_that_it_is_not_a_validation():
    ok = {s: {"dates": 100, "events": 500, "gamma": g, "t": t} for s, g, t in (("無控制", 0.013, 4.0), ("A", 0.010, 2.5), ("B", 0.002, 0.5))}
    text = xp.render({"s_stretch": ok, "s_no_volume_high": ok})
    assert "不是驗證" in text and "暴露調整後存活" in text and "77%" in text and "規格 B 與 s_no_volume_high 只當參考" in text
    bad = {**ok, "A": {**ok["A"], "t": 1.0}}
    assert "暴露調整後不存活" in xp.render({"s_stretch": bad, "s_no_volume_high": ok})


def test_main_runs_end_to_end_on_synthetic_prices_and_writes_a_report(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    days, stocks = 360, 30
    close = 50 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, (days, stocks)), axis=0))
    open_ = np.vstack([close[:1], close[:-1]]) * (1 + rng.normal(0, 0.004, close.shape))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, close.shape)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, close.shape)))
    as32 = lambda a: a.astype(np.float32)  # noqa: E731
    data = {"dates": pd.bdate_range("2013-06-03", periods=days).to_numpy().astype("datetime64[ns]"),
            "symbols": np.array([str(1100 + i) for i in range(stocks)]), "adj_open": as32(open_), "adj_high": as32(high),
            "adj_low": as32(low), "adj_close": as32(close), "volume": as32(rng.lognormal(14, 0.4, close.shape)), "close": as32(close)}
    monkeypatch.setattr(study, "OUT", tmp_path)
    monkeypatch.setattr(study, "get_prices", lambda cache, refresh, limit: data)
    monkeypatch.setattr(sys, "argv", ["signal_rules_exposure.py", "--min-index-stocks", "10"])
    assert xp.main() == 0
    text = next(tmp_path.glob("exposure_*.md")).read_text(encoding="utf-8")
    assert "| s_stretch | A |" in text and "| s_no_volume_high | B |" in text and "判定（s_stretch，規格 A" in text


def test_events_are_deduplicated_to_the_first_signal_per_stock_within_twenty_days(null):
    mask, premise, live, expo, windows = world("null")
    expected = len(ss.dedupe(*np.nonzero(mask & live))[0])
    assert null["A"]["events"] == expected < int(mask.sum())


def test_render_shows_a_dash_instead_of_a_ratio_when_the_uncontrolled_estimate_is_missing():
    nan = {"dates": 0, "events": 0, "gamma": float("nan"), "t": float("nan")}
    text = xp.render({"s_stretch": {"無控制": nan, "A": nan, "B": nan}, "s_no_volume_high": {"無控制": nan, "A": nan, "B": nan}})
    assert "nan" not in text and "暴露調整後不存活" in text
