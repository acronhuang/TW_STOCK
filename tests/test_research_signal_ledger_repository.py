"""TDD: 研究訊號成效帳本只能 append，不可覆寫。"""

from datetime import date, datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from src.research_signal_ledger.models import (
    ResearchSignalOutcome,
    ResearchSignalSnapshot,
    SignalDirection,
)
from src.research_signal_ledger.repository import ResearchSignalLedgerRepository


pytestmark = pytest.mark.unit


class FakeCollection:
    def __init__(self, key_fields):
        self.documents = []
        self.key_fields = key_fields
        self.update_calls = []

    def create_index(self, *args, **kwargs):
        return kwargs.get("name")

    def insert_one(self, document):
        if any(
            all(existing[field] == document[field] for field in self.key_fields)
            for existing in self.documents
        ):
            raise DuplicateKeyError("duplicate")
        self.documents.append(document)

    def find_one(self, query, sort=None):
        matches = [
            document
            for document in self.documents
            if all(document.get(field) == value for field, value in query.items())
        ]
        if not matches:
            return None
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda document: document[field], reverse=direction < 0)
        return dict(matches[0])


class FakeDatabase:
    def __init__(self):
        self.collections = {
            "research_signal_snapshots": FakeCollection(("snapshot_key",)),
            "research_benchmark_snapshots": FakeCollection(("benchmark_key",)),
            "research_signal_outcomes": FakeCollection(
                ("snapshot_key", "horizon_trading_days", "revision")
            ),
            "research_signal_capture_runs": FakeCollection(("run_id", "source")),
            "research_method_status": FakeCollection(("source", "signal_kind", "policy_version")),
            "research_method_status_history": FakeCollection(("source", "signal_kind", "policy_version")),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.fixture
def snapshot():
    return ResearchSignalSnapshot(
        snapshot_key="a" * 64,
        source="daily_picks",
        source_event_id="sha256:abc:2026-10-10",
        symbol="2330",
        analysis_date=date(2026, 10, 10),
        available_at=datetime(2026, 10, 10, 20, tzinfo=timezone.utc),
        captured_at=datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
        signal_kind="factor_rank",
        direction=SignalDirection.LONG,
        evaluation_enabled=True,
        price_at_signal=100.0,
        source_payload={"rank": 1},
        benchmark_profile="market_equal_weight_liquid_tw_v1",
        rule_version="daily_picks_v1",
    )


@pytest.fixture
def outcome(snapshot):
    return ResearchSignalOutcome(
        outcome_key="outcome:1",
        snapshot_key=snapshot.snapshot_key,
        horizon_trading_days=5,
        revision=1,
        entry_date=date(2026, 10, 13),
        exit_date=date(2026, 10, 20),
        entry_adj_close=100.0,
        exit_adj_close=110.0,
        direction=SignalDirection.LONG,
        gross_return_pct=10.0,
        net_return_pct=9.415,
        excess_mkt_pct=8.0,
        excess_pool_pct=None,
        hit=True,
        cost_pct=0.585,
        price_data_as_of=datetime(2026, 10, 20, 20, tzinfo=timezone.utc),
        evaluated_at=datetime(2026, 10, 20, 21, tzinfo=timezone.utc),
    )


@pytest.fixture
def repository():
    return ResearchSignalLedgerRepository(FakeDatabase())


def test_duplicate_snapshot_is_idempotent_without_update(repository, snapshot):
    first = repository.insert_snapshots([snapshot])
    second = repository.insert_snapshots([snapshot])

    assert first.inserted == 1
    assert second.duplicates == 1
    assert repository.snapshots.update_calls == []


def test_outcome_revision_cannot_replace_prior_revision(repository, outcome):
    assert repository.append_outcome(outcome) is True
    assert repository.append_outcome(outcome) is False
    assert repository.outcomes.update_calls == []


@pytest.mark.integration
def test_mongo_unique_indexes_reject_duplicate_snapshot_and_outcome(write_db, snapshot, outcome):
    repository = ResearchSignalLedgerRepository(write_db)
    for collection in (
        repository.snapshots,
        repository.benchmarks,
        repository.outcomes,
        repository.capture_runs,
    ):
        collection.delete_many({})

    repository.snapshots.insert_one(snapshot.model_dump(mode="json"))
    with pytest.raises(DuplicateKeyError):
        repository.snapshots.insert_one(snapshot.model_dump(mode="json"))

    repository.outcomes.insert_one(outcome.model_dump(mode="json"))
    with pytest.raises(DuplicateKeyError):
        repository.outcomes.insert_one(outcome.model_dump(mode="json"))


@pytest.mark.integration
def test_latest_outcome_returns_highest_revision_without_removing_history(
    write_db, snapshot, outcome
):
    repository = ResearchSignalLedgerRepository(write_db)
    repository.outcomes.delete_many({})
    revision_two = outcome.model_copy(
        update={
            "outcome_key": "outcome:2",
            "revision": 2,
            "supersedes_outcome_key": outcome.outcome_key,
        }
    )

    assert repository.append_outcome(outcome) is True
    assert repository.append_outcome(revision_two) is True

    latest = repository.latest_outcome(snapshot.snapshot_key, 5)
    assert latest is not None
    assert latest.revision == 2
    assert repository.outcomes.count_documents({}) == 2


def test_load_method_status_reads_current_status_without_mutation():
    database = FakeDatabase()
    database.collections["research_method_status"] = FakeCollection(("source", "signal_kind", "policy_version"))
    database.collections["research_method_status_history"] = FakeCollection(("source", "signal_kind", "policy_version"))
    database.collections["research_method_status"].documents.append(
        {
            "source": "daily_picks",
            "signal_kind": "factor_rank",
            "policy_version": "v1",
            "state": "observe",
            "effective_weight": 1.0,
            "evaluated_horizon": 20,
            "sample_size": 0,
            "independent_analysis_days": 0,
            "failure_streak": 0,
            "reason": "insufficient mature evidence",
            "decided_at": "2026-10-10T00:00:00+00:00",
            "evidence_outcome_keys": [],
        }
    )
    repository = ResearchSignalLedgerRepository(database)

    status = repository.load_method_status("daily_picks", "factor_rank", "v1")

    assert status is not None
    assert status.state == "observe"
    assert database.collections["research_method_status"].update_calls == []