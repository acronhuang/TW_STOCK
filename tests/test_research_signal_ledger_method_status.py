"""TDD: 方法狀態 repository：現態可更新，歷程只 append。"""

from datetime import datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError

from src.research_signal_ledger.models import MethodStatus
from src.research_signal_ledger.repository import ResearchSignalLedgerRepository


pytestmark = pytest.mark.unit


class Collection:
    def __init__(self, key_fields):
        self.documents = []
        self.key_fields = key_fields
        self.insert_calls = 0
        self.replace_calls = 0

    def create_index(self, *args, **kwargs):
        return kwargs.get("name")

    def insert_one(self, document):
        self.insert_calls += 1
        if any(all(d[f] == document[f] for f in self.key_fields) for d in self.documents):
            raise DuplicateKeyError("duplicate")
        self.documents.append(document)

    def replace_one(self, query, document, upsert=False):
        self.replace_calls += 1
        for index, existing in enumerate(self.documents):
            if all(existing.get(k) == v for k, v in query.items()):
                self.documents[index] = document
                return
        if upsert:
            self.documents.append(document)

    def find_one(self, query, sort=None):
        for document in self.documents:
            if all(document.get(k) == v for k, v in query.items()):
                return dict(document)
        return None


class Database:
    def __init__(self):
        self.collections = {
            "research_signal_snapshots": Collection(("snapshot_key",)),
            "research_benchmark_snapshots": Collection(("benchmark_key",)),
            "research_signal_outcomes": Collection(("snapshot_key", "horizon_trading_days", "revision")),
            "research_signal_capture_runs": Collection(("run_id", "source")),
            "research_method_status": Collection(("source", "signal_kind", "policy_version")),
            "research_method_status_history": Collection(("source", "signal_kind", "policy_version", "decided_at")),
        }

    def __getitem__(self, name):
        return self.collections[name]


def status(state="observe", weight=1.0, decided_hour=1):
    return MethodStatus(
        source="daily_picks",
        signal_kind="factor_rank",
        policy_version="v1",
        state=state,
        effective_weight=weight,
        evaluated_horizon=20,
        sample_size=60,
        independent_analysis_days=20,
        failure_streak=0,
        reason="test",
        decided_at=datetime(2026, 11, 1, decided_hour, tzinfo=timezone.utc),
        evidence_outcome_keys=[],
    )


def test_saving_a_status_replaces_the_current_row_and_appends_history():
    database = Database()
    repository = ResearchSignalLedgerRepository(database)

    repository.save_method_status(status("observe", 1.0, 1))
    repository.save_method_status(status("degraded", 0.75, 2))

    assert len(database["research_method_status"].documents) == 1
    assert repository.load_method_status("daily_picks", "factor_rank", "v1").state == "degraded"
    assert len(database["research_method_status_history"].documents) == 2


def test_history_is_never_replaced():
    database = Database()
    repository = ResearchSignalLedgerRepository(database)

    repository.save_method_status(status("observe", 1.0, 1))
    repository.save_method_status(status("degraded", 0.75, 2))

    assert database["research_method_status_history"].replace_calls == 0
    states = [d["state"] for d in database["research_method_status_history"].documents]
    assert states == ["observe", "degraded"]


def test_resaving_an_identical_decision_does_not_duplicate_history():
    database = Database()
    repository = ResearchSignalLedgerRepository(database)

    repository.save_method_status(status("observe", 1.0, 1))
    repository.save_method_status(status("observe", 1.0, 1))

    assert len(database["research_method_status_history"].documents) == 1


@pytest.mark.integration
def test_real_mongo_keeps_one_current_row_but_every_historical_decision(write_db):
    for name in ("research_method_status", "research_method_status_history"):
        write_db[name].delete_many({})
    repository = ResearchSignalLedgerRepository(write_db)

    repository.save_method_status(status("observe", 1.0, 1))
    repository.save_method_status(status("degraded", 0.75, 2))
    repository.save_method_status(status("degraded", 0.75, 2))

    assert write_db["research_method_status"].count_documents({}) == 1
    assert write_db["research_method_status_history"].count_documents({}) == 2
    assert repository.load_method_status("daily_picks", "factor_rank", "v1").state == "degraded"
