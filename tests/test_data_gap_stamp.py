"""TDD: 公告型資料的適用日（交易日當天、非交易日取下一個交易日）。"""

from datetime import datetime

import pytest

from src.data_gap import stamp

pytestmark = pytest.mark.unit

CALENDAR = ["2026-09-23", "2026-09-24", "2026-09-29", "2026-10-07", "2026-10-08", "2026-10-12"]


def test_on_a_trading_day_the_announcement_applies_to_that_day():
    assert stamp.applicable_day(datetime(2026, 10, 8, 17, 30), CALENDAR) == datetime(2026, 10, 8)


def test_on_a_holiday_or_weekend_it_applies_to_the_next_trading_day():
    assert stamp.applicable_day(datetime(2026, 10, 9, 17, 30), CALENDAR) == datetime(2026, 10, 12)
    assert stamp.applicable_day(datetime(2026, 10, 11, 21, 0), CALENDAR) == datetime(2026, 10, 12)


def test_a_long_closure_walks_forward_across_every_missing_day():
    assert stamp.applicable_day(datetime(2026, 9, 25, 17, 30), CALENDAR) == datetime(2026, 9, 29)
    assert stamp.applicable_day(datetime(2026, 9, 28, 9, 0), CALENDAR) == datetime(2026, 9, 29)


def test_without_a_later_trading_day_the_fetch_date_is_kept_instead_of_guessing():
    assert stamp.applicable_day(datetime(2026, 12, 31), CALENDAR) == datetime(2026, 12, 31)


def test_time_of_day_is_dropped_so_keys_stay_stable_across_runs():
    assert stamp.applicable_day(datetime(2026, 10, 8, 0, 1), CALENDAR) == stamp.applicable_day(datetime(2026, 10, 8, 23, 59), CALENDAR)
