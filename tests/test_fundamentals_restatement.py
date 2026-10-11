"""TDD: 財報重編版本歷史（quarterly_earnings 被覆寫前保存舊版，供時點回測）。"""

from datetime import datetime

import pytest

from src.fundamentals import restatement

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 11, 7, 0)
T1 = datetime(2026, 10, 25, 7, 0)
KEY = ("2330", 2026, 2)


def quarter(net_income=706780923000.0, **overrides):
    doc = {"symbol": "2330", "year": 2026, "season": 2, "report_type": "合併", "data_source": "TWSE_OpenAPI",
           "income": {"revenue": 1270380250000, "net_income": net_income, "eps": 27.25, "unit_fixed": True},
           "balance": {"total_equity": 6474470981000.0, "source": "OpenAPI", "unit_fixed": True},
           "cashflow": {}, "updated_at": T0}
    doc.update(overrides)
    return doc


def run(docs, stored=None, now=T0):
    stored = stored or {}
    hashes = {k: (v["version"], v["content_hash"]) for k, v in stored.items()}
    return restatement.build_actions(docs, hashes, lambda key: stored[key], now)


def first_version(doc=None, now=T0):
    actions, _ = run([doc or quarter()], now=now)
    return actions[0]["doc"]


def test_a_quarter_seen_for_the_first_time_becomes_a_baseline_version_one():
    actions, summary = run([quarter()])

    version = actions[0]["doc"]
    assert actions[0]["op"] == "insert"
    assert (version["symbol"], version["year"], version["season"], version["version"]) == ("2330", 2026, 2, 1)
    assert version["baseline"] is True and version["observed_at"] == T0
    assert version["income"]["net_income"] == 706780923000.0
    assert summary == {"baseline": 1, "restated": 0, "merged": 0, "unchanged": 0}


def test_an_unchanged_quarter_writes_nothing_even_if_only_updated_at_moves():
    stored = {KEY: first_version()}

    actions, summary = run([quarter(updated_at=T1)], stored, T1)

    assert actions == [] and summary["unchanged"] == 1


def test_a_changed_existing_value_creates_the_next_version_and_names_the_changed_field():
    stored = {KEY: first_version()}

    actions, summary = run([quarter(net_income=650000000000.0)], stored, T1)

    version = actions[0]["doc"]
    assert version["version"] == 2 and version["baseline"] is False and version["observed_at"] == T1
    assert version["changed_fields"] == ["income.net_income"]
    assert version["income"]["net_income"] == 650000000000.0
    assert summary["restated"] == 1


def test_a_data_source_swap_is_flagged_so_it_is_not_mistaken_for_a_company_restatement():
    stored = {KEY: first_version(quarter(data_source="FinMind_Paid"))}

    actions, _ = run([quarter(net_income=650000000000.0, data_source="TWSE_OpenAPI")], stored, T1)

    assert actions[0]["doc"]["source_changed"] is True


def test_filling_a_previously_missing_field_merges_into_the_current_version_without_a_new_one():
    stored = {KEY: first_version(quarter(balance={}))}

    actions, summary = run([quarter()], stored, T1)

    assert actions[0]["op"] == "merge" and actions[0]["id"] == stored[KEY]["_id"]
    assert actions[0]["set"]["balance"]["total_equity"] == 6474470981000.0
    assert summary["merged"] == 1 and summary["restated"] == 0


def test_float_noise_and_meta_flags_are_not_restatements():
    stored = {KEY: first_version()}
    noisy = quarter(net_income=706780923000.5)
    noisy["income"]["unit_fixed"] = False
    noisy["balance"]["source"] = "FinMind"

    actions, summary = run([noisy], stored, T1)

    assert actions == [] and summary["unchanged"] == 1


def test_a_field_that_disappears_from_the_source_does_not_count_as_a_change():
    stored = {KEY: first_version()}

    actions, _ = run([quarter(income={"revenue": 1270380250000})], stored, T1)

    assert actions == []


def test_version_numbers_continue_from_the_stored_latest():
    v1 = first_version()
    v2 = {**v1, "_id": "2330:2026:2:v2", "version": 2, "baseline": False, "observed_at": T1,
          "content_hash": restatement.content_hash(restatement.flatten(quarter(net_income=1.0)))}
    v2["income"] = quarter(net_income=1.0)["income"]

    actions, _ = run([quarter(net_income=2.0)], {KEY: v2}, T1)

    assert actions[0]["doc"]["version"] == 3


def test_as_of_picks_the_latest_version_already_observed_and_always_trusts_the_baseline():
    v1 = {"version": 1, "baseline": True, "observed_at": T1}
    v2 = {"version": 2, "baseline": False, "observed_at": datetime(2026, 11, 20)}

    assert restatement.version_as_of([v1, v2], datetime(2026, 8, 1))["version"] == 1
    assert restatement.version_as_of([v1, v2], datetime(2026, 11, 19))["version"] == 1
    assert restatement.version_as_of([v1, v2], datetime(2026, 11, 20))["version"] == 2
    assert restatement.version_as_of([], datetime(2026, 11, 20)) is None
