"""TDD: 基本面選股法的每日落地（謝富旭成長精選、品質成長、阿甘護城河）。"""

import json
from datetime import date

import pytest

from scripts import persist_screen_signals as module


pytestmark = pytest.mark.unit


class FakeScreens:
    """三個掃描的替身；記錄呼叫次數以證明每個掃描每次只算一次。"""

    def __init__(self):
        self.calls = []

    def hsieh_growth(self):
        self.calls.append("hsieh_growth")
        return [{"symbol": "2330", "name": "台積電", "price": 900.0, "dividend_yield": 1.5, "eps_yoy": 20.0}]

    def quality_growth(self):
        self.calls.append("quality_growth")
        return [{"symbol": "2317", "name": "鴻海", "price": 200.0, "roe": 15.5, "opm": 12.0}]

    def agan(self):
        self.calls.append("agan")
        return []


def test_each_screen_is_written_under_its_own_directory_with_the_data_day(tmp_path):
    screens = FakeScreens()

    written = module.persist_all(tmp_path, date(2026, 10, 9), screens)

    assert sorted(path.name for path in written) == [
        "agan_moat_20261009.json",
        "hsieh_growth_20261009.json",
        "quality_growth_20261009.json",
    ]
    assert (tmp_path / "hsieh_growth" / "hsieh_growth_20261009.json").exists()


def test_rows_keep_the_screen_fields_and_the_data_day(tmp_path):
    module.persist_all(tmp_path, date(2026, 10, 9), FakeScreens())

    payload = json.loads((tmp_path / "quality_growth" / "quality_growth_20261009.json").read_text(encoding="utf-8"))

    assert payload["data_date"] == "2026-10-09"
    assert payload["rows"][0]["symbol"] == "2317"
    assert payload["rows"][0]["roe"] == 15.5


def test_an_empty_screen_still_writes_a_file(tmp_path):
    module.persist_all(tmp_path, date(2026, 10, 9), FakeScreens())

    payload = json.loads((tmp_path / "agan_moat" / "agan_moat_20261009.json").read_text(encoding="utf-8"))

    assert payload["rows"] == []


def test_each_screen_runs_exactly_once(tmp_path):
    screens = FakeScreens()

    module.persist_all(tmp_path, date(2026, 10, 9), screens)

    assert sorted(screens.calls) == ["agan", "hsieh_growth", "quality_growth"]


def test_one_failing_screen_does_not_stop_the_others(tmp_path):
    class Broken(FakeScreens):
        def quality_growth(self):
            raise RuntimeError("db down")

    written = module.persist_all(tmp_path, date(2026, 10, 9), Broken())

    assert sorted(path.name for path in written) == ["agan_moat_20261009.json", "hsieh_growth_20261009.json"]
    assert not (tmp_path / "quality_growth").exists()


def test_a_failure_is_reported_through_the_exit_code(tmp_path, monkeypatch):
    class Broken(FakeScreens):
        def agan(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(module, "build_screens", lambda: Broken())
    monkeypatch.setattr(module, "latest_data_day", lambda: date(2026, 10, 9))
    monkeypatch.setattr(module, "RESULTS_DIR", tmp_path)

    assert module.main([]) == 1
