"""TDD: 上游腳本的每日訊號落地（只新增，不影響原流程）。"""

import json
from datetime import date, datetime

import pytest

from src.research_signal_ledger.persistence import write_daily_signals


pytestmark = pytest.mark.unit


def test_writes_a_dated_json_file_with_the_data_day_in_the_name(tmp_path):
    path = write_daily_signals(tmp_path, "obv_bottom", date(2026, 10, 8), [{"symbol": "2330", "close": 100.0}])

    assert path == tmp_path / "obv_bottom" / "obv_bottom_20261008.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["data_date"] == "2026-10-08"
    assert payload["rows"] == [{"symbol": "2330", "close": 100.0}]


def test_an_empty_result_still_writes_a_file_so_no_signal_is_distinguishable_from_not_run(tmp_path):
    path = write_daily_signals(tmp_path, "obv_bottom", date(2026, 10, 8), [])

    assert json.loads(path.read_text(encoding="utf-8"))["rows"] == []


def test_a_same_day_rerun_never_overwrites_the_earlier_file(tmp_path):
    first = write_daily_signals(tmp_path, "obv_bottom", date(2026, 10, 8), [{"symbol": "2330"}])
    second = write_daily_signals(tmp_path, "obv_bottom", date(2026, 10, 8), [{"symbol": "2317"}])

    assert first != second
    assert json.loads(first.read_text(encoding="utf-8"))["rows"] == [{"symbol": "2330"}]
    assert json.loads(second.read_text(encoding="utf-8"))["rows"] == [{"symbol": "2317"}]


def test_datetime_data_days_are_accepted_as_stock_price_dates(tmp_path):
    path = write_daily_signals(tmp_path, "core_signals", datetime(2026, 10, 8, 0, 0), [])

    assert path.name == "core_signals_20261008.json"


def test_failure_to_persist_never_raises_to_the_caller(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where a directory is needed", encoding="utf-8")

    assert write_daily_signals(blocker, "obv_bottom", date(2026, 10, 8), []) is None
