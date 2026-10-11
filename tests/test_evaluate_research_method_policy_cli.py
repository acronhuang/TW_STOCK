"""TDD: 方法政策 CLI 的分組、單向決策與寫入邊界。"""

from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from scripts import evaluate_research_method_policy as module
from src.research_signal_ledger.models import MethodStatus
from src.research_signal_ledger.policy import PolicyConfig


pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Snapshot:
    snapshot_key: str
    source: str
    signal_kind: str
    analysis_date: date
    evaluation_enabled: bool = True


@dataclass(frozen=True)
class Outcome:
    snapshot_key: str
    outcome_key: str
    revision: int
    net_return_pct: float
    excess_mkt_pct: float
    hit: bool | None


def _failing_rows(source="daily_picks", kind="factor_rank", days=20, per_day=3, revision=1):
    snapshots, outcomes = [], []
    for day in range(days):
        for n in range(per_day):
            key = f"{source}-{kind}-{day}-{n}"
            snapshots.append(Snapshot(key, source, kind, date(2026, 10, 1 + day % 28)))
            outcomes.append(Outcome(key, f"{key}:{revision}", revision, -1.0, -1.0, False))
    return snapshots, outcomes


def test_outcomes_are_grouped_per_method_and_use_only_the_latest_revision():
    snapshots, outcomes = _failing_rows(days=1, per_day=1)
    key = snapshots[0].snapshot_key
    outcomes.append(Outcome(key, f"{key}:2", 2, 5.0, 5.0, True))

    groups = module.group_latest_outcomes(snapshots, outcomes)

    rows = groups[("daily_picks", "factor_rank")]
    assert [row.revision for row in rows] == [2]
    assert rows[0].net_return_pct == 5.0


def test_snapshots_that_are_not_evaluable_are_excluded_from_governance():
    snapshots, outcomes = _failing_rows(days=1, per_day=1)
    snapshots = [Snapshot(s.snapshot_key, s.source, s.signal_kind, s.analysis_date, False) for s in snapshots]

    assert module.group_latest_outcomes(snapshots, outcomes) == {}


def test_two_methods_are_decided_independently():
    s1, o1 = _failing_rows("daily_picks", "factor_rank", days=20, per_day=3)
    s2, o2 = _failing_rows("technical", "vcp", days=3, per_day=3)

    decisions = module.decide_all(s1 + s2, o1 + o2, lambda *_: None, PolicyConfig())

    assert decisions[("daily_picks", "factor_rank")].failure_streak == 1
    assert decisions[("technical", "vcp")].reason == "insufficient mature evidence"


class FakeRepository:
    def __init__(self, prior=None):
        self.prior = prior
        self.saved = []
        self.snapshots = []

    def load_method_status(self, source, signal_kind, policy_version):
        return self.prior

    def save_method_status(self, status):
        self.saved.append(status)


def test_dry_run_writes_nothing(monkeypatch, capsys):
    snapshots, outcomes = _failing_rows(days=20, per_day=3)
    repository = FakeRepository()
    monkeypatch.setattr(module, "get_db", lambda: object())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "load_snapshots_and_outcomes", lambda *_: (snapshots, outcomes))

    assert module.main(["--horizon", "20", "--policy-version", "v1", "--dry-run"]) == 0

    assert repository.saved == []
    assert "daily_picks/factor_rank" in capsys.readouterr().out


def test_a_decision_without_a_new_round_is_not_persisted(monkeypatch):
    snapshots, outcomes = _failing_rows(days=20, per_day=3)
    prior = MethodStatus(
        source="daily_picks", signal_kind="factor_rank", policy_version="v1", state="observe",
        effective_weight=1.0, evaluated_horizon=20, sample_size=60, independent_analysis_days=20,
        failure_streak=1, reason="x", decided_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        evidence_outcome_keys=[],
    )
    repository = FakeRepository(prior)
    monkeypatch.setattr(module, "get_db", lambda: object())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "load_snapshots_and_outcomes", lambda *_: (snapshots, outcomes))
    monkeypatch.setattr(module, "notify_transition", lambda *_: None)

    module.main(["--horizon", "20", "--policy-version", "v1"])

    assert repository.saved == []


def test_a_new_round_is_persisted_and_a_state_change_is_announced(monkeypatch):
    snapshots, outcomes = _failing_rows(days=26, per_day=3)
    prior = MethodStatus(
        source="daily_picks", signal_kind="factor_rank", policy_version="v1", state="observe",
        effective_weight=1.0, evaluated_horizon=20, sample_size=60, independent_analysis_days=20,
        failure_streak=1, reason="x", decided_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        evidence_outcome_keys=[],
    )
    repository = FakeRepository(prior)
    announced = []
    monkeypatch.setattr(module, "get_db", lambda: object())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "load_snapshots_and_outcomes", lambda *_: (snapshots, outcomes))
    monkeypatch.setattr(module, "notify_transition", lambda *args: announced.append(args))

    module.main(["--horizon", "20", "--policy-version", "v1"])

    assert [s.state for s in repository.saved] == ["degraded"]
    assert repository.saved[0].effective_weight == 0.75
    assert len(announced) == 1
