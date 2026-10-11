"""TDD: 開機補跑——主機停機後自動補抓最新日、補缺口並通知。"""

from datetime import datetime, timedelta

import pytest

from src.ops import boot_catchup

pytestmark = pytest.mark.unit

BOOT = datetime(2026, 9, 19, 21, 10)
LONG_DOWN = datetime(2026, 9, 15, 19, 56)


def build(**overrides):
    log = {"notify": [], "execute": []}

    def execute(command):
        log["execute"].append(command)

    def notify(message):
        log["notify"].append(message)

    options = dict(
        wait_mongo=lambda: True, notify=notify, execute=execute,
        repair=lambda: {"detected": 12, "repaired": 3, "unrecoverable": 9},
        boot_start=BOOT, previous_boot_end=LONG_DOWN,
    )
    options.update(overrides)
    return log, options


def test_a_long_downtime_catches_up_the_latest_day_repairs_gaps_and_notifies():
    log, options = build()

    summary = boot_catchup.run(**options)

    assert [c[0] for c in log["execute"]] == ["twse_openapi_sync.py", "twse_daily_update.py"]
    assert len(log["notify"]) == 1
    assert "4 天 1 小時" in log["notify"][0] and "已補 3" in log["notify"][0] and "無法回補 9" in log["notify"][0]
    assert summary["caught_up"] is True


def test_a_short_reboot_does_nothing_and_stays_quiet():
    log, options = build(previous_boot_end=BOOT - timedelta(minutes=2))

    summary = boot_catchup.run(**options)

    assert log["execute"] == [] and log["notify"] == [] and summary["caught_up"] is False


def test_unknown_downtime_is_treated_as_long_and_says_so():
    log, options = build(previous_boot_end=None)

    boot_catchup.run(**options)

    assert len(log["execute"]) == 2
    assert "無法判定" in log["notify"][0]


def test_mongodb_never_coming_up_is_reported_instead_of_running_blind():
    log, options = build(wait_mongo=lambda: False)

    summary = boot_catchup.run(**options)

    assert log["execute"] == [] and summary["caught_up"] is False
    assert "MongoDB" in log["notify"][0]


def test_a_failing_catch_up_command_is_reported_and_the_rest_still_runs():
    def execute(command):
        if command[0] == "twse_openapi_sync.py":
            raise RuntimeError("TWSE blocked")

    log, options = build(execute=execute)

    boot_catchup.run(**options)

    assert "twse_openapi_sync" in log["notify"][0] and "失敗" in log["notify"][0]
    assert "已補 3" in log["notify"][0]
