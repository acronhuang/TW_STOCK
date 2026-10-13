"""TDD: FinMind 額度檢查——有 402 要失敗，無日誌、日誌停了、輪次不足都不能當成通過，只看最近 N 輪。"""

from datetime import datetime, timedelta

import pytest

from scripts import check_finmind_quota as script
from src.ops import finmind_quota as fq

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 13, 10, 20)


def make_logs(tmp_path, count=72, with_402=None, last=None):
    """count 輪每小時日誌，最新一輪在 last（預設 10:05）；with_402 是 {第幾輪(0=最新): 402 次數}。"""
    last = last or datetime(2026, 10, 13, 10, 5, 1)
    with_402 = with_402 or {}
    for n in range(count):
        stamp = last - timedelta(hours=n)
        body = "09:05 | INFO | ok\n" + "09:05 | ERROR | HTTP 錯誤: 402\n" * with_402.get(n, 0)
        (tmp_path / f"hourly_update_{stamp:%Y%m%d_%H%M%S}.log").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_quiet_stretch_passes(tmp_path):
    ok, message, hits = fq.check(make_logs(tmp_path), NOW)

    assert ok and hits == [] and "72 輪" in message


def test_a_run_with_402_fails_and_names_the_run_and_the_count(tmp_path):
    ok, message, hits = fq.check(make_logs(tmp_path, with_402={9: 51}), NOW)

    assert not ok and hits == [(datetime(2026, 10, 13, 1, 5, 1), 51)]
    assert "10-13 01:05(51)" in message and "共 51 次" in message


def test_a_402_older_than_the_window_is_not_counted(tmp_path):
    logs = make_logs(tmp_path, count=80, with_402={75: 143})

    assert fq.check(logs, NOW, runs=72)[0] is True
    assert fq.check(logs, NOW, runs=80)[0] is False


def test_no_logs_is_no_data_not_a_pass(tmp_path):
    ok, message, _ = fq.check(tmp_path, NOW)

    assert not ok and message.startswith("無資料")


def test_logs_that_stopped_arriving_are_no_data_even_if_clean(tmp_path):
    stale = make_logs(tmp_path, last=datetime(2026, 10, 12, 6, 5, 1))

    ok, message, _ = fq.check(stale, NOW)

    assert not ok and "無資料" in message and "超過 3 小時" in message


def test_too_few_runs_to_judge_is_reported_instead_of_passing(tmp_path):
    ok, message, _ = fq.check(make_logs(tmp_path, count=10), NOW, runs=72)

    assert not ok and "輪次不足" in message and "只有 10 輪" in message


def test_files_that_are_not_hourly_logs_are_ignored(tmp_path):
    make_logs(tmp_path, count=24)
    (tmp_path / "daily_summary_20261013.log").write_text("HTTP 錯誤: 402\n" * 5, encoding="utf-8")

    assert fq.check(tmp_path, NOW, runs=24)[0] is True


def test_the_script_exits_nonzero_for_a_402_and_zero_for_a_clean_window(tmp_path, capsys, monkeypatch):
    class FixedClock:
        @staticmethod
        def now():
            return NOW

    monkeypatch.setattr(script, "datetime", FixedClock)
    bad, good = tmp_path / "bad", tmp_path / "good"
    bad.mkdir()
    good.mkdir()
    make_logs(bad, with_402={3: 2})
    make_logs(good)

    assert script.main(["--log-dir", str(bad), "--runs", "24"]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert script.main(["--log-dir", str(good), "--runs", "24"]) == 0
