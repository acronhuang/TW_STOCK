"""TDD: 快照型最新日表的真實日期對應（交易日標記與非交易日標記）。"""

import pytest

from src.data_gap import redate

pytestmark = pytest.mark.unit

CAL = ["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-24", "2026-09-29", "2026-10-07", "2026-10-08", "2026-10-12"]


def test_data_date_tables_move_every_stamp_back_to_the_previous_trading_day():
    assert redate.true_day("2026-09-21", CAL, "data") == "2026-09-18"
    assert redate.true_day("2026-10-08", CAL, "data") == "2026-10-07"


def test_a_holiday_snapshot_of_a_data_date_table_is_the_previous_trading_days_data_just_like_the_next_days_stamp():
    assert redate.true_day("2026-10-09", CAL, "data") == "2026-10-08"
    assert redate.true_day("2026-09-20", CAL, "data") == "2026-09-18"
    assert redate.true_day("2026-09-25", CAL, "data") == redate.true_day("2026-09-29", CAL, "data") == "2026-09-24"


def test_announcement_tables_keep_trading_day_stamps_and_move_holiday_snapshots_to_the_next_trading_day():
    assert redate.true_day("2026-10-08", CAL, "applicable") == "2026-10-08"
    assert redate.true_day("2026-10-09", CAL, "applicable") == "2026-10-12"
    assert redate.true_day("2026-09-25", CAL, "applicable") == redate.true_day("2026-09-29", CAL, "applicable") == "2026-09-29"


def test_a_stamp_with_no_target_day_in_the_calendar_is_reported_as_none():
    assert redate.true_day("2026-09-01", CAL, "data") is None
    assert redate.true_day("2027-01-05", CAL, "applicable") is None


def test_the_day_map_covers_every_stamped_day_and_collapses_holiday_duplicates_onto_one_target():
    stamped = ["2026-09-18", "2026-09-20", "2026-09-21"]

    assert redate.day_map(stamped, CAL, "data") == {"2026-09-18": "2026-09-17", "2026-09-20": "2026-09-18",
                                                     "2026-09-21": "2026-09-18"}


def test_every_table_has_exactly_one_semantic():
    assert set(redate.SEMANTICS) == {"odd_lot_trading", "after_hours_trading", "foreign_top20",
                                     "securities_lending", "etf_dca_rank", "margin_suspension"}
    assert {redate.SEMANTICS[t] for t in ("odd_lot_trading", "after_hours_trading", "foreign_top20")} == {"data"}
    assert {redate.SEMANTICS[t] for t in ("securities_lending", "etf_dca_rank", "margin_suspension")} == {"applicable"}
