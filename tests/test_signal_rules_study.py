"""TDD: 訊號驗證腳本的串接——結果檔、留存期只能跑一次、判定規則套用、報告格式。用合成資料，不連資料庫。"""

import json
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from scripts import signal_rules_study as study
from src.analysis import signal_rules as sr
from src.analysis import signal_study as ss

pytestmark = pytest.mark.unit


def synthetic(stocks=25, days=520, seed=1):
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = synthetic()
    monkeypatch.setattr(study, "OUT", tmp_path)
    monkeypatch.setattr(study, "get_prices", lambda cache, refresh, limit: data)
    monkeypatch.setitem(study.SPLITS, "holdout", (datetime(2014, 9, 1), datetime(2015, 4, 30)))

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["signal_rules_study.py", "--min-index-stocks", "10", *args])
        return study.main()

    return run, tmp_path


def test_dev_run_writes_a_report_and_a_result_for_every_rule(env):
    run, out = env
    assert run("--split", "dev") == 0
    result = json.loads((out / "result_dev.json").read_text(encoding="utf-8"))
    assert set(result["results"]) == {*sr.ENTRY_RULES, *sr.SELL_RULES, *sr.FILTER_RULES}
    assert all(isinstance(v["fdr_significant"], bool) for v in result["results"].values())
    assert result["params"] == sr.PARAMS and list(out.glob("report_dev_*.md"))
    assert any(np.isfinite(v["t"]) for v in result["results"].values())  # --min-index-stocks 有傳到指數計算
    assert not (out / "holdout_done.json").exists()


def test_holdout_is_refused_without_a_dev_result(env):
    run, _ = env
    with pytest.raises(SystemExit, match="尚未有開發期結果"):
        run("--split", "holdout")


def test_holdout_runs_once_then_is_locked_unless_forced(env):
    run, out = env
    run("--split", "dev")
    assert run("--split", "holdout") == 0
    verdict = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
    assert set(verdict) == {*sr.ENTRY_RULES, *sr.SELL_RULES, *sr.FILTER_RULES}
    assert set(verdict.values()) <= {ss.SUPPORTED, ss.NOT_SUPPORTED, ss.INSUFFICIENT}
    assert (out / "holdout_done.json").exists()
    with pytest.raises(SystemExit, match="不重跑"):
        run("--split", "holdout")
    assert run("--split", "holdout", "--force-holdout") == 0
    assert json.loads((out / "holdout_done.json").read_text(encoding="utf-8"))["force"] is True


def test_a_limited_smoke_run_writes_no_result_files(env, capsys):
    run, out = env
    assert run("--split", "dev", "--limit-symbols", "10") == 0
    assert not (out / "result_dev.json").exists() and "冒煙測試" in capsys.readouterr().out


def test_verdicts_apply_the_pre_registered_rule_per_rule():
    good = {"days": 100, "events": 500, "mean": 0.01, "fdr_significant": True}
    dev = {"pullback_end": good, "s_trend_turn": {**good, "mean": -0.01}, "blk_warn": {**good, "mean": -0.01}}
    hold = {"pullback_end": good, "s_trend_turn": {**good, "mean": -0.02, "fdr_significant": False}, "blk_warn": {**good, "mean": 0.03}}
    assert study.verdicts(dev, hold) == {"pullback_end": ss.SUPPORTED, "s_trend_turn": ss.NOT_SUPPORTED, "blk_warn": ss.NOT_SUPPORTED}


def test_directions_follow_the_hypotheses():
    assert all(study.DIRECTION[r] == +1 for r in sr.ENTRY_RULES)
    assert all(study.DIRECTION[r] == -1 for r in (*sr.SELL_RULES, *sr.FILTER_RULES))


def test_pct_formatting_and_missing_values():
    assert study.pct(0.01234) == "+1.23%" and study.pct(-0.005) == "-0.50%"
    assert study.pct(float("nan")).strip() == "—" and study.pct(None).strip() == "—"


def test_report_lists_every_rule_with_the_fixed_criteria_and_the_survivorship_warning(env):
    run, out = env
    run("--split", "dev")
    text = next(out.glob("report_dev_*.md")).read_text(encoding="utf-8")
    assert all(name in text for name in (*sr.ENTRY_RULES, *sr.SELL_RULES, *sr.FILTER_RULES))
    assert f"反應日 ≥ {ss.MIN_DAYS}" in text and "存活者偏誤" in text and "t+2..t+21" in text


def test_universe_excludes_thin_or_penny_stocks(monkeypatch):
    data = synthetic(stocks=3, days=300)
    data["volume"][:, 0] = 100.0                # 成交值太低
    data["close"][:, 1] = 5.0                   # 股價低於 10 元（未還原收盤）
    data["volume"][:, 1] = 1e8                  # 成交值仍足夠，只有股價這一項會把它排除
    masks, universe = study.detect(data)
    assert not universe[:, 0].any() and not universe[:, 1].any() and universe[200:, 2].any()
    assert masks["premise"].shape == data["adj_close"].shape


def test_stocks_with_too_little_history_are_skipped():
    data = synthetic(stocks=2, days=100)
    masks, universe = study.detect(data)
    assert not universe.any() and not any(m.any() for m in masks.values())


def with_forward(monkeypatch, run):
    monkeypatch.setitem(study.SPLITS, "forward", (datetime(2014, 9, 1), None))
    run("--split", "dev")
    run("--split", "holdout")


def test_forward_needs_the_holdout_result_first(env, monkeypatch):
    run, _ = env
    monkeypatch.setitem(study.SPLITS, "forward", (datetime(2014, 9, 1), None))
    with pytest.raises(SystemExit, match="尚未有留存期結果"):
        run("--split", "forward")


def test_forward_before_the_registered_date_is_refused_unless_exploratory(env, monkeypatch, capsys):
    run, out = env
    with_forward(monkeypatch, run)
    monkeypatch.setattr(study, "FORWARD_EARLIEST", datetime(2999, 1, 1))
    with pytest.raises(SystemExit, match="預先登記"):
        run("--split", "forward")
    assert run("--split", "forward", "--exploratory") == 0
    assert "探索性" in capsys.readouterr().out
    assert not (out / "forward_done.json").exists() and not (out / "result_forward.json").exists()


def test_forward_runs_once_after_the_registered_date_and_judges_only_the_two_rules(env, monkeypatch):
    run, out = env
    with_forward(monkeypatch, run)
    monkeypatch.setattr(study, "FORWARD_EARLIEST", datetime(2020, 1, 1))
    assert run("--split", "forward") == 0
    verdict = json.loads((out / "verdict_forward.json").read_text(encoding="utf-8"))
    assert set(verdict) == set(study.FORWARD_RULES) == {"s_stretch", "s_no_volume_high"}
    assert set(verdict.values()) <= {ss.SUPPORTED, ss.NOT_SUPPORTED, ss.INSUFFICIENT}
    assert (out / "forward_done.json").exists()
    with pytest.raises(SystemExit, match="不重跑"):
        run("--split", "forward")
    assert run("--split", "forward", "--force-forward") == 0


def test_forward_window_stops_one_longest_window_before_the_latest_data(monkeypatch):
    data = synthetic()
    masks, universe = study.detect(data)
    excess, _ = ss.build_excess(data["adj_close"].astype(float), min_stocks=10)
    monkeypatch.setitem(study.SPLITS, "forward", (datetime(2013, 6, 1), None))
    full = study.run_split("forward", data, masks, universe, ss.Windows(excess))["s_no_volume_high"]["events"]
    monkeypatch.setitem(study.SPLITS, "forward", (datetime(2013, 6, 1), datetime(2030, 1, 1)))
    assert full < study.run_split("forward", data, masks, universe, ss.Windows(excess))["s_no_volume_high"]["events"]


def test_forward_verdicts_use_a_one_sided_bonferroni_threshold():
    base = {"days": 100, "events": 500, "mean": 0.01, "t": 2.4, "p": 0.04}
    prev = {"s_stretch": base, "s_no_volume_high": base}
    fwd = {"s_stretch": {**base, "p": 0.04}, "s_no_volume_high": {**base, "p": 0.06}}  # 單尾 0.02 與 0.03
    assert study.forward_verdicts(prev, fwd) == {"s_stretch": ss.SUPPORTED, "s_no_volume_high": ss.NOT_SUPPORTED}
    fwd_negative = {name: {**base, "mean": -0.01, "t": -2.4} for name in study.FORWARD_RULES}
    assert set(study.forward_verdicts(prev, fwd_negative).values()) == {ss.NOT_SUPPORTED}
