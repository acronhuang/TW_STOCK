"""TDD: 穩健性檢查——切面固定、事件先去重再切、成交值分組時基準也同組、不做通過與否的判定。"""

import sys

import numpy as np
import pandas as pd
import pytest

from scripts import signal_rules_robustness as rb
from scripts import signal_rules_study as study
from src.analysis import signal_rules as sr
from src.analysis import signal_study as ss

pytestmark = pytest.mark.unit


def synthetic(stocks=25, days=520, seed=3):
    rng = np.random.default_rng(seed)
    shape = (days, stocks)
    close = 50 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, shape), axis=0))
    open_ = np.vstack([close[:1], close[:-1]]) * (1 + rng.normal(0, 0.004, shape))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, shape)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, shape)))
    as32 = lambda a: a.astype(np.float32)  # noqa: E731
    return {
        "dates": pd.bdate_range("2013-06-03", periods=days).to_numpy().astype("datetime64[ns]"),
        "symbols": np.array([str(1100 + i) for i in range(stocks)]),
        "adj_open": as32(open_), "adj_high": as32(high), "adj_low": as32(low), "adj_close": as32(close),
        "volume": as32(rng.lognormal(14, 0.4, shape)), "close": as32(close),
    }


def test_the_slices_are_the_pre_registered_ones():
    assert rb.RULES == ("s_stretch", "s_no_volume_high")
    assert [(n, lo, hi) for n, lo, hi in rb.LIQUIDITY] == [("成交值 2千萬~1億", 2e7, 1e8), ("成交值 1億~5億", 1e8, 5e8), ("成交值 5億以上", 5e8, float("inf"))]
    assert rb.VARIANTS == {"s_stretch": ("stretch_bias", (0.10, 0.20)), "s_no_volume_high": ("nohigh_vol", (0.5, 0.9))}
    assert rb.STATE_WINDOW == 20


def test_market_state_uses_the_trailing_twenty_day_sum_and_flags_the_warmup():
    market = np.array([0.01] * 20 + [-0.30] + [0.0] * 4)
    positive, enough = rb.market_state(market, window=20)
    assert not enough[:20].any() and enough[20:].all()
    assert positive[19] and not positive[20]          # 第 20 列起看最近 20 列的和：0.20 變成 −0.11
    assert rb.market_state(np.array([0.0, 0.01, -0.02, 0.0]), window=2)[0].tolist() == [False, True, False, False]


def test_variant_labels_change_only_the_named_parameter():
    labels = dict(rb.variant_labels("s_stretch"))
    assert set(labels) == {"s_stretch stretch_bias=0.1", "s_stretch stretch_bias=0.2"}
    for params in labels.values():
        assert {k: v for k, v in params.items() if k != "stretch_bias"} == {k: v for k, v in sr.PARAMS.items() if k != "stretch_bias"}


@pytest.fixture(scope="module")
def built():
    data = synthetic()
    masks, premise, universe, value = rb.build_masks(data)
    excess, market = ss.build_excess(data["adj_close"].astype(float), min_stocks=10)
    return data, masks, premise, universe, value, ss.Windows(excess), market


def test_build_masks_has_the_base_rule_and_every_variant_and_the_base_matches_the_study_detector(built):
    data, masks, premise, universe, value, _, _ = built
    assert set(masks) == {"s_stretch", "s_no_volume_high", "s_stretch stretch_bias=0.1", "s_stretch stretch_bias=0.2",
                          "s_no_volume_high nohigh_vol=0.5", "s_no_volume_high nohigh_vol=0.9"}
    reference, ref_universe = study.detect(data)
    assert (masks["s_stretch"] == reference["s_stretch"]).all() and (premise == reference["premise"]).all() and (universe == ref_universe).all()
    assert np.isfinite(value[universe]).all()


def test_slices_cover_all_registered_groups_in_order_and_the_pieces_add_up(built):
    data, masks, premise, universe, value, windows, market = built
    live = universe & ((data["dates"] >= np.datetime64(rb.PERIOD[0])) & (data["dates"] <= np.datetime64(rb.PERIOD[1])))[:, None]
    slices = rb.slices_for("s_no_volume_high", masks, premise, live, value, windows, data["dates"], market)
    names = [n for n, _ in slices]
    assert names[:4] == ["全期間", "2013 年", "2014 年", "2015 年"]
    assert names[4:] == ["成交值 2千萬~1億", "成交值 1億~5億", "成交值 5億以上", "大盤前 20 日為正", "大盤前 20 日為負", "nohigh_vol=0.5", "nohigh_vol=0.9"]
    by = dict(slices)
    assert sum(by[f"{y} 年"]["events"] for y in (2013, 2014, 2015)) == by["全期間"]["events"]
    assert by["全期間"]["events"] > 0


def test_market_state_slices_split_the_events_without_overlap(built):
    data, masks, premise, universe, value, windows, market = built
    live = universe & np.ones(universe.shape[0], dtype=bool)[:, None]
    by = dict(rb.slices_for("s_no_volume_high", masks, premise, live, value, windows, data["dates"], market))
    assert by["大盤前 20 日為正"]["events"] + by["大盤前 20 日為負"]["events"] <= by["全期間"]["events"]


def test_summary_counts_only_slices_with_enough_days_and_lists_significant_negatives():
    def s(mean, t, days):
        return {"mean": mean, "t": t, "days": days, "events": 100}

    slices = [("全期間", s(-0.05, -9, 500)), ("a", s(0.02, 2.5, 100)), ("b", s(-0.01, -2.5, 100)), ("c", s(-0.01, -1.0, 100)),
              ("d", s(0.03, 3.0, 5)), ("e", s(float("nan"), float("nan"), 100)), ("f", s(-0.01, -2.0, 20))]
    got = rb.summarize(slices)
    # 全期間不計；反應日剛好 20 的 f 算數；t 剛好 −2 算顯著為負
    assert got == {"usable": 4, "positive": 1, "significantly_negative": ["b", "f"], "skipped": ["d", "e"]}


def test_report_has_no_pass_fail_verdict_and_states_it_is_not_a_validation(built, tmp_path, monkeypatch, capsys):
    data, *_ = built
    monkeypatch.setattr(study, "OUT", tmp_path)
    monkeypatch.setattr(study, "get_prices", lambda cache, refresh, limit: data)
    monkeypatch.setattr(sys, "argv", ["signal_rules_robustness.py", "--min-index-stocks", "10"])
    assert rb.main() == 0
    text = next(tmp_path.glob("robustness_*.md")).read_text(encoding="utf-8")
    assert "不是驗證" in text and "## s_stretch" in text and "## s_no_volume_high" in text
    assert "方向為正的切面" in text and "支持" not in text and "不支持" not in text


def test_market_state_window_sum_drops_the_oldest_day_once_the_window_is_full():
    positive, _ = rb.market_state(np.array([0.5, 0.0, 0.0, 0.0, -0.01, 0.0]), window=3)
    assert positive.tolist() == [True, True, True, False, False, False]


# ---- 手工構造的小世界：每個切面的歸屬與基準都能心算 ----
RATES = [0.001, 0.002, 0.003, 0.004]          # 四檔每天固定的超額報酬
VALUES = [5e7, 1e8, 5e8, 3e8]                  # 近 20 日平均成交值：剛好落在組別邊界的有 1億 與 5億


@pytest.fixture(scope="module")
def tiny():
    days = 80
    dates = pd.bdate_range("2013-12-02", periods=days).to_numpy().astype("datetime64[ns]")   # 第 5 列在 2013、第 30 列在 2014
    excess = np.full((days, 4), np.nan)
    excess[1:] = RATES
    market = np.zeros(days)
    market[:31] = 0.001                                                                         # 第 30 列前 20 日累計為正；第 5 列在暖機期
    masks = {rule: np.zeros((days, 4), dtype=bool) for rule in ("s_stretch", *[label for label, _ in rb.variant_labels("s_stretch")])}
    masks["s_stretch"][30, :] = True
    masks["s_stretch"][5, 0] = True
    ones = np.ones((days, 4), dtype=bool)
    value = np.tile(np.array(VALUES, dtype=np.float32), (days, 1))
    return dict(slices=dict(rb.slices_for("s_stretch", masks, ones, ones, value, ss.Windows(excess), dates, market)), windows=ss.Windows(excess))


def test_events_are_split_by_year_with_the_boundary_day_in_the_right_year(tiny):
    s = tiny["slices"]
    assert (s["全期間"]["events"], s["2013 年"]["events"], s["2014 年"]["events"]) == (5, 1, 4)


def test_liquidity_bands_include_the_lower_edge_and_exclude_the_upper_edge(tiny):
    s = tiny["slices"]
    # 1億剛好屬於中間組、5億剛好屬於最高組；第一檔在兩個日子各有一個事件
    assert (s["成交值 2千萬~1億"]["events"], s["成交值 1億~5億"]["events"], s["成交值 5億以上"]["events"]) == (2, 2, 1)


def test_each_liquidity_band_is_compared_with_its_own_band_not_the_whole_market(tiny):
    s = tiny["slices"]
    for name in ("成交值 2千萬~1億", "成交值 1億~5億", "成交值 5億以上"):
        assert s[name]["mean"] == pytest.approx(0.0, abs=1e-12)   # 事件與同組基準完全相同；若拿全市場當基準就不是 0


def test_market_state_slices_skip_the_warmup_rows_and_use_the_requested_sign(tiny):
    s = tiny["slices"]
    assert (s["大盤前 20 日為正"]["events"], s["大盤前 20 日為負"]["events"]) == (4, 0)


def test_threshold_variants_with_no_events_still_appear_with_zero_events(tiny):
    s = tiny["slices"]
    assert s["stretch_bias=0.1"]["events"] == 0 and s["stretch_bias=0.2"]["events"] == 0


def test_evaluate_and_baseline_use_the_primary_window_of_twenty_days(tiny):
    windows = tiny["windows"]
    zero_baseline = (np.array([30]), np.array([0.0]))
    assert rb.evaluate(np.array([30]), np.array([0]), windows, zero_baseline)["mean"] == pytest.approx(0.02)   # 20 日 × 0.001
    days, means = rb.baseline_of(np.pad(np.ones((1, 1), dtype=bool), ((30, 49), (0, 3))), windows)
    assert days.tolist() == [30] and means[0] == pytest.approx(0.02)
