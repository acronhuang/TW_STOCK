"""TDD: 帳本 dashboard read model 只能讀取最新成熟結果。"""

from dataclasses import dataclass

from dashboard.pages.research_signal_ledger import ledger_read_model


@dataclass(frozen=True)
class Outcome:
    snapshot_key: str
    horizon_trading_days: int
    revision: int
    net_return_pct: float
    gross_return_pct: float
    excess_mkt_pct: float | None


class FakeRepository:
    def __init__(self):
        self.write_calls = []

    def list_outcomes(self, horizon):
        return [
            Outcome("snapshot-1", horizon, 1, 1.0, 1.5, 0.5),
            Outcome("snapshot-1", horizon, 2, 3.2, 3.7, 2.1),
        ]


def test_ledger_page_uses_latest_outcome_revision_and_never_mutates_status():
    repository = FakeRepository()

    rows = ledger_read_model(repository, horizon=20)

    assert rows == [
        {
            "snapshot_key": "snapshot-1",
            "gross_return_pct": 3.7,
            "net_return_pct": 3.2,
            "excess_mkt_pct": 2.1,
        }
    ]
    assert repository.write_calls == []