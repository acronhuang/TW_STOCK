"""TDD: 停機時間計算與外部看門狗 ping。"""

from datetime import datetime, timedelta

import pytest

from src.ops import downtime, healthcheck

pytestmark = pytest.mark.unit


def test_downtime_is_the_gap_between_the_previous_boot_end_and_this_boot():
    assert downtime.gap(datetime(2026, 9, 15, 19, 56), datetime(2026, 9, 19, 21, 10)) == timedelta(days=4, hours=1, minutes=14)


def test_unknown_previous_boot_means_unknown_downtime():
    assert downtime.gap(None, datetime(2026, 9, 19, 21, 10)) is None


def test_a_negative_gap_is_treated_as_unknown_instead_of_nonsense():
    assert downtime.gap(datetime(2026, 9, 19, 21, 10), datetime(2026, 9, 15, 19, 56)) is None


@pytest.mark.parametrize("delta, text", [
    (timedelta(days=4, hours=1, minutes=14), "4 天 1 小時"),
    (timedelta(hours=3, minutes=20), "3 小時 20 分鐘"),
    (timedelta(minutes=35), "35 分鐘"),
    (None, "無法判定"),
])
def test_describe_is_human_readable(delta, text):
    assert downtime.describe(delta) == text


def test_ping_without_a_url_does_nothing_and_reports_false():
    calls = []

    assert healthcheck.ping(None, get=lambda *a, **k: calls.append(a)) is False
    assert healthcheck.ping("", get=lambda *a, **k: calls.append(a)) is False
    assert calls == []


def test_ping_calls_the_url_with_a_timeout():
    seen = {}

    def get(url, timeout):
        seen.update(url=url, timeout=timeout)

    assert healthcheck.ping("https://hc.example/abc", get=get) is True
    assert seen == {"url": "https://hc.example/abc", "timeout": 10}


def test_a_failing_ping_never_breaks_the_job():
    def boom(url, timeout):
        raise ConnectionError("offline")

    assert healthcheck.ping("https://hc.example/abc", get=boom) is False
