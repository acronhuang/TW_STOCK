"""TDD: 異機備份標記檔——太舊或不存在都要判為異常，不能當成通過。"""

import os
from datetime import datetime, timedelta

import pytest

from scripts import check_offsite_backup as script
from src.ops import offsite_backup as ob

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 13, 10, 15)


def marker(tmp_path, age_days, name="tw_stock_analysis_20261013_010001.tar.gz"):
    path = tmp_path / "last_pull_ok"
    path.write_text(name + "\n", encoding="utf-8")
    stamp = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_a_recent_pull_is_fine_and_names_the_file(tmp_path):
    ok, message = ob.check(marker(tmp_path, 1), NOW)

    assert ok and "20261013_010001" in message


def test_a_pull_older_than_the_limit_is_a_failure_that_says_how_many_days(tmp_path):
    ok, message = ob.check(marker(tmp_path, 6), NOW)

    assert not ok and "6 天" in message and "TwStock_PullBackup" in message


def test_the_limit_itself_still_passes_and_one_day_over_does_not(tmp_path):
    assert ob.check(marker(tmp_path, 4), NOW)[0] is True
    assert ob.check(marker(tmp_path, 5), NOW)[0] is False


def test_no_marker_is_no_data_not_a_pass(tmp_path):
    ok, message = ob.check(tmp_path / "missing", NOW)

    assert not ok and "沒有成功紀錄" in message


def test_the_script_exits_nonzero_for_a_stale_marker_and_zero_for_a_fresh_one(tmp_path, capsys):
    stale = marker(tmp_path, 9)
    assert script.main(["--marker", str(stale)]) == 1
    assert "FAIL" in capsys.readouterr().out

    fresh = marker(tmp_path, 0)
    os.utime(fresh, None)
    assert script.main(["--marker", str(fresh)]) == 0
