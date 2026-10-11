"""TDD: 月營收缺口偵測（次月 10 日公告期限，加 OpenAPI 換月延遲的寬限至 15 日）。"""

from datetime import date

import pytest

from src.data_gap import policy, revenue

pytestmark = pytest.mark.unit

FULL = {"2026-06": 1970, "2026-07": 1980, "2026-08": 1969}


def test_within_the_grace_period_the_previous_month_is_not_expected_yet():
    assert revenue.thin_months(FULL, date(2026, 10, 15)) == []


def test_after_the_grace_period_a_month_with_no_rows_is_a_gap():
    assert revenue.thin_months(FULL, date(2026, 10, 16)) == ["2026-09"]


def test_a_month_below_ninety_percent_of_the_recent_baseline_is_a_gap():
    assert revenue.thin_months({**FULL, "2026-09": 1500}, date(2026, 10, 20)) == ["2026-09"]


def test_a_normally_complete_month_is_not_a_gap():
    assert revenue.thin_months({**FULL, "2026-09": 1900}, date(2026, 10, 20)) == []


def test_an_older_month_that_stayed_short_is_still_reported():
    counts = {"2026-05": 1960, "2026-06": 1970, "2026-07": 1980, "2026-08": 100, "2026-09": 1950}

    assert revenue.thin_months(counts, date(2026, 10, 20)) == ["2026-08"]


def test_without_any_baseline_nothing_can_be_judged():
    assert revenue.thin_months({}, date(2026, 10, 20)) == []


def test_the_month_arithmetic_crosses_the_year_boundary():
    counts = {"2025-09": 1960, "2025-10": 1970, "2025-11": 1975}

    assert revenue.thin_months(counts, date(2026, 1, 20)) == ["2025-12"]


def test_gap_days_use_the_first_of_the_month_so_the_register_key_is_stable():
    assert revenue.gap_day("2026-09") == "20260901"


def test_policy_resyncs_from_the_official_openapi():
    recovery = policy.recovery_for("monthly_revenue", "20260901")

    assert recovery.mode == "backfill"
    assert recovery.commands == (("sync_revenue_openapi.py",),)
