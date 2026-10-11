"""TDD: 非交易日被標上資料的列（抓取日誤當資料日）的清理規劃。"""

import pytest

from src.data_gap import phantom

pytestmark = pytest.mark.unit

CAL = ["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-24", "2026-09-29", "2026-10-08", "2026-10-12"]


def rows(mapping):
    return lambda day: mapping.get(day, 0)


def test_the_previous_trading_day_skips_weekends_holidays_and_closures():
    assert phantom.previous_trading_day("2026-09-28", CAL) == "2026-09-24"
    assert phantom.previous_trading_day("2026-10-09", CAL) == "2026-10-08"
    assert phantom.previous_trading_day("2026-09-01", CAL) is None


def test_phantom_days_are_the_stamped_days_that_are_not_trading_days_after_the_cutoff():
    stamped = ["2026-09-18", "2026-09-20", "2026-09-25", "2026-02-15", "2026-10-09"]

    assert phantom.phantom_days(stamped, CAL, since="2026-03-01") == ["2026-09-20", "2026-09-25", "2026-10-09"]


def test_a_phantom_day_is_relabelled_when_its_true_day_has_no_rows_so_the_missing_day_is_recovered():
    actions = phantom.plan("after_hours_trading", ["2026-09-20"], CAL, rows({"2026-09-20": 29743}))

    assert actions == [{"op": "relabel", "collection": "after_hours_trading", "from": "2026-09-20", "to": "2026-09-18"}]


def test_margin_is_deleted_because_the_official_by_date_data_already_overwrote_the_true_day():
    counts = {"2026-10-09": 1298, "2026-10-08": 1298}

    [action] = phantom.plan("margin_purchase_short_sale", ["2026-10-09"], CAL, rows(counts))

    assert action == {"op": "delete", "collection": "margin_purchase_short_sale", "from": "2026-10-09"}


@pytest.mark.parametrize("collection,key", [("after_hours_trading", "stock_id"), ("odd_lot_trading", "stock_id"),
                                            ("securities_lending", "twse_code"), ("foreign_top20", "rank")])
def test_other_tables_merge_the_phantom_rows_into_the_true_day_because_the_trading_day_rows_lag_by_one_day(collection, key):
    counts = {"2026-10-09": 1235, "2026-10-08": 1234}

    [action] = phantom.plan(collection, ["2026-10-09"], CAL, rows(counts))

    assert action == {"op": "merge", "collection": collection, "from": "2026-10-09", "to": "2026-10-08", "key": key}


def test_two_phantom_days_with_the_same_true_day_fill_it_once_then_the_second_merges_over_it():
    counts = {"2026-09-25": 28772, "2026-09-28": 28772}

    actions = phantom.plan("after_hours_trading", ["2026-09-25", "2026-09-28"], CAL, rows(counts))

    assert [a["op"] for a in actions] == ["relabel", "merge"]
    assert actions[0]["to"] == "2026-09-24" and actions[1]["to"] == "2026-09-24"


def test_a_phantom_day_without_any_earlier_trading_day_is_left_alone():
    assert phantom.plan("after_hours_trading", ["2026-09-01"], CAL, rows({"2026-09-01": 5})) == []


def test_the_stamped_collections_are_exactly_the_ones_with_a_cleanup_rule():
    assert phantom.plan("stock_price", ["2026-10-09"], CAL, rows({"2026-10-09": 5})) == []
    assert set(phantom.COLLECTIONS) == {"after_hours_trading", "odd_lot_trading", "margin_purchase_short_sale",
                                        "securities_lending", "foreign_top20", "etf_dca_rank", "margin_suspension"}
