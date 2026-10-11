"""TDD: OpenAPI 只給最新已公布交易日的資料；非交易日抓到的資料屬於前一個交易日，不能標成抓取日。"""

from datetime import datetime

import pytest

from src.data_gap import stamp

pytestmark = pytest.mark.unit

CALENDAR = ["2026-09-23", "2026-09-24", "2026-09-29", "2026-10-07", "2026-10-08", "2026-10-12"]


def test_on_a_trading_day_the_fetch_date_is_the_stamp():
    assert stamp.stamp_day(datetime(2026, 10, 8, 21, 5), CALENDAR) == datetime(2026, 10, 8)


def test_on_a_national_holiday_the_data_belongs_to_the_previous_trading_day():
    assert stamp.stamp_day(datetime(2026, 10, 9, 9, 5), CALENDAR) == datetime(2026, 10, 8)


def test_on_a_weekend_the_data_belongs_to_the_last_trading_day_before_it():
    assert stamp.stamp_day(datetime(2026, 10, 11, 14, 0), CALENDAR) == datetime(2026, 10, 8)


def test_a_long_closure_walks_back_across_every_missing_day():
    assert stamp.stamp_day(datetime(2026, 9, 28, 9, 0), CALENDAR) == datetime(2026, 9, 24)


def test_without_any_earlier_trading_day_the_fetch_date_is_kept_instead_of_guessing():
    assert stamp.stamp_day(datetime(2026, 9, 1), CALENDAR) == datetime(2026, 9, 1)


def test_time_of_day_is_dropped_so_keys_stay_stable_across_hourly_runs():
    assert stamp.stamp_day(datetime(2026, 10, 8, 0, 1), CALENDAR) == stamp.stamp_day(datetime(2026, 10, 8, 23, 59), CALENDAR)
