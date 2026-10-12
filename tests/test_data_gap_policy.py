"""TDD: 缺口回補政策——哪些缺口能自動補、哪些不能、哪些不該補。"""

import pytest

from src.data_gap import policy

pytestmark = pytest.mark.unit


def test_stock_price_is_backfilled_by_date_with_apply():
    recovery = policy.recovery_for("stock_price", "20260915")

    assert recovery.mode == "backfill"
    assert ("backfill_by_date.py", "--date", "20260915", "--apply") in recovery.commands


def test_institutional_flow_uses_the_range_tool_for_the_single_day():
    recovery = policy.recovery_for("institutional_flow", "20260916")

    assert recovery.mode == "backfill"
    assert ("institutional_backfill.py", "--start", "2026-09-16", "--end", "2026-09-16") in recovery.commands


def test_margin_runs_both_markets_because_a_thin_day_does_not_say_which_side_is_missing():
    recovery = policy.recovery_for("margin_purchase_short_sale", "20260917")

    scripts = {command[0] for command in recovery.commands}
    assert scripts == {"backfill_margin_by_date.py", "tpex_margin_sync.py"}
    assert all("--apply" in c for c in recovery.commands if c[0] == "backfill_margin_by_date.py")


@pytest.mark.parametrize("collection", ["day_trading_targets", "securities_lending"])
def test_latest_day_only_sources_are_unrecoverable_with_a_reason(collection):
    recovery = policy.recovery_for(collection, "20260917")

    assert recovery.mode == "unrecoverable"
    assert recovery.commands == ()
    assert "最新" in recovery.reason


def test_derived_factors_are_not_backfilled_here():
    recovery = policy.recovery_for("stock_factors", "20260917")

    assert recovery.mode == "derived" and recovery.commands == ()


@pytest.mark.parametrize("collection,kind", [("after_hours_trading", "after_hours"), ("odd_lot_trading", "odd")])
def test_after_hours_and_odd_lot_are_refetched_from_the_official_by_date_endpoints(collection, kind):
    recovery = policy.recovery_for(collection, "20260917")

    assert recovery.mode == "backfill"
    assert recovery.commands == (("official_day_sync.py", "--kinds", kind, "--date", "20260917", "--apply"),)


def test_an_unknown_collection_needs_review_instead_of_guessing():
    assert policy.recovery_for("something_new", "20260917").mode == "review"


def test_foreign_holding_is_refetched_for_the_single_day_from_the_by_date_endpoint():
    recovery = policy.recovery_for("foreign_holding", "20260916")

    assert recovery.mode == "backfill"
    assert recovery.commands == (("twse_foreign_holding_sync.py", "--date", "20260916"),)


def test_risk_analysis_is_a_decision_snapshot_that_cannot_be_recreated_after_the_fact():
    recovery = policy.recovery_for("risk_analysis", "20260916")

    assert recovery.mode == "snapshot" and recovery.commands == ()
    assert "快照" in recovery.reason


def test_the_price_calendar_is_repaired_before_tables_that_depend_on_it():
    assert policy.priority("stock_price") < policy.priority("institutional_flow")
    assert policy.priority("stock_price") < policy.priority("margin_purchase_short_sale")
