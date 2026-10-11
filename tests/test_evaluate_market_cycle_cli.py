"""TDD: 市場週期評估 CLI 讀取歷史 picks 並唯讀報告。"""

import json
from datetime import date

import pytest

from scripts import evaluate_market_cycle as module


pytestmark = pytest.mark.unit


def write_pick(directory, stamp, day_iso, cycle):
    (directory / f"picks_{stamp}.json").write_text(
        json.dumps({"date": day_iso, "pku": {"cycle": {"cycle": cycle}}}), encoding="utf-8"
    )


def test_calls_are_read_from_dated_picks_files(tmp_path):
    write_pick(tmp_path, "20261005_203000", "2026-10-05T20:30:00", "summer")
    write_pick(tmp_path, "20261006_203000", "2026-10-06T20:30:00", "autumn")

    calls = module.load_cycle_calls(tmp_path)

    assert [(c.day, c.cycle) for c in calls] == [(date(2026, 10, 5), "summer"), (date(2026, 10, 6), "autumn")]


def test_the_last_report_of_a_day_wins(tmp_path):
    write_pick(tmp_path, "20261005_090000", "2026-10-05T09:00:00", "summer")
    write_pick(tmp_path, "20261005_203000", "2026-10-05T20:30:00", "autumn")

    assert [(c.day, c.cycle) for c in module.load_cycle_calls(tmp_path)] == [(date(2026, 10, 5), "autumn")]


def test_unreadable_or_cycle_less_files_are_skipped(tmp_path):
    (tmp_path / "picks_20261005_000000.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "picks_20261006_000000.json").write_text(json.dumps({"date": "2026-10-06T10:00:00"}), encoding="utf-8")
    write_pick(tmp_path, "20261007_203000", "2026-10-07T20:30:00", "summer")

    assert [(c.day, c.cycle) for c in module.load_cycle_calls(tmp_path)] == [(date(2026, 10, 7), "summer")]


def test_the_report_states_when_a_cycle_has_too_little_evidence():
    result = {
        "samples": 4, "mean_buy_hold_pct": 1.0, "mean_timed_pct": 0.5, "mean_edge_pct": -0.5,
        "by_cycle": {"winter": {"samples": 2, "mean_buy_hold_pct": -1.0, "mean_timed_pct": 0.0,
                                "mean_edge_pct": 1.0, "conclusive": False}},
    }

    report = module.format_report(5, result)

    assert "證據不足" in report
    assert "winter" in report
