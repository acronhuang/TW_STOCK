"""TDD: 成熟評估 CLI 不可替未成熟快照產生 outcome。"""

from datetime import date, datetime, timezone

from scripts import evaluate_research_signals as module
from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection


class FakeRepository:
    def __init__(self, database):
        self.outcomes = []

    def append_outcome(self, outcome):
        self.outcomes.append(outcome)
        return True


UNRIPE_SNAPSHOT = object()


def _snapshot(available=datetime(2026, 10, 8, 20, tzinfo=timezone.utc)):
    return ResearchSignalSnapshot(
        snapshot_key="a" * 64,
        source="daily_picks",
        source_event_id="sha256:abc:2026-10-08",
        symbol="2330",
        analysis_date=date(2026, 10, 8),
        available_at=available,
        captured_at=available,
        signal_kind="factor_rank",
        direction=SignalDirection.LONG,
        evaluation_enabled=True,
        price_at_signal=100.0,
        source_payload={},
        benchmark_profile="market_equal_weight_liquid_tw_v1",
        rule_version="v1",
    )


def test_pending_horizons_skips_horizons_that_already_have_an_outcome():
    class Repository:
        def latest_outcome(self, snapshot_key, horizon):
            return object() if horizon == 5 else None

    pending = module.pending_horizons(Repository(), _snapshot(), (5, 10, 20), date(2026, 12, 31))

    assert pending == (10, 20)


def test_pending_horizons_skips_horizons_that_cannot_be_mature_yet():
    class Repository:
        def latest_outcome(self, snapshot_key, horizon):
            return None

    # 5 個交易日至少要 5 個日曆日；as_of 距可用日只有 3 天，三個 horizon 都不可能成熟。
    assert module.pending_horizons(Repository(), _snapshot(), (5, 10, 20), date(2026, 10, 11)) == ()
    assert module.pending_horizons(Repository(), _snapshot(), (5, 10, 20), date(2026, 10, 14)) == (5,)


def test_dry_run_reports_without_appending(monkeypatch, capsys):
    repository = FakeRepository(None)
    outcome = object()
    monkeypatch.setattr(module, "get_db", lambda: object())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "load_eligible_snapshots", lambda *_: [_snapshot()])
    monkeypatch.setattr(module, "pending_horizons", lambda *_: (5,))
    monkeypatch.setattr(module, "evaluate_snapshot_outcomes", lambda *_: [outcome])

    assert module.main(["--as-of", "2026-12-31", "--dry-run"]) == 0

    assert repository.outcomes == []
    assert "would_append=1" in capsys.readouterr().out


def test_evaluation_cli_skips_unripe_snapshot(monkeypatch):
    repository = FakeRepository(None)
    monkeypatch.setattr(module, "get_db", lambda: object())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "load_eligible_snapshots", lambda *_: [_snapshot()])
    monkeypatch.setattr(module, "pending_horizons", lambda *_: (5,))
    monkeypatch.setattr(module, "evaluate_snapshot_outcomes", lambda *_: [])

    assert module.main(["--horizons", "5,10,20", "--as-of", "2026-10-10"]) == 0
    assert repository.outcomes == []