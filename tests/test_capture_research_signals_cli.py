"""TDD: 訊號擷取 CLI 必須隔離單一來源失敗。"""

from dataclasses import dataclass

from scripts import capture_research_signals as module
from src.research_signal_ledger.sources.base import SourceCollectionResult


@dataclass
class WriteResult:
    inserted: int
    duplicates: int


class FakeRepository:
    def __init__(self, database):
        self.snapshots = []
        self.runs = []

    def insert_snapshots(self, snapshots):
        self.snapshots.extend(snapshots)
        return WriteResult(inserted=len(snapshots), duplicates=0)

    def record_capture_run(self, run):
        self.runs.append(run)


class EmptyPriceCollection:
    def find(self, query, projection=None):
        return []

    def distinct(self, field, query):
        return []


class FakeDatabase:
    def __getitem__(self, name):
        assert name in {"stock_price", "team_analysis"}
        return EmptyPriceCollection()


class FailingSource:
    name = "failing_source"

    def collect(self, as_of):
        raise RuntimeError("source unavailable")


class GoodSource:
    name = "good_source"

    def collect(self, as_of):
        return SourceCollectionResult(self.name, [object()], "captured")


def test_capture_cli_records_failed_source_without_blocking_other_sources(monkeypatch, capsys):
    repository = FakeRepository(None)
    monkeypatch.setattr(module, "get_db", lambda: FakeDatabase())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [FailingSource(), GoodSource()])

    assert module.main(["--as-of", "2026-10-10"]) == 1

    assert len(repository.snapshots) == 1
    assert {run.source for run in repository.runs} == {"failing_source", "good_source"}
    assert "good_source captured=1" in capsys.readouterr().out


def test_capture_market_benchmark_appends_current_membership():
    class BenchmarkRepository:
        def __init__(self):
            self.snapshot = None

        def insert_benchmark(self, snapshot):
            self.snapshot = snapshot
            return True

    repository = BenchmarkRepository()
    assert module.capture_market_benchmark(repository, [
        ("2330", "2026-10-10", 100.0), ("2317", "2026-10-10", 50.0)
    ], "2026-10-10") is True
    assert repository.snapshot.symbols == ["2317", "2330"]


def test_benchmark_price_rows_accepts_decimal128_adjusted_close():
    from bson.decimal128 import Decimal128

    rows = module.benchmark_price_rows(
        [{"symbol": "2330", "adj_close": Decimal128("2550.0")},
         {"symbol": "2317", "adj_close": Decimal128("0")}],
        "2026-10-08",
    )

    assert rows == [("2330", "2026-10-08", 2550.0)]


def test_price_query_uses_datetime_range_for_the_as_of_day():
    from datetime import date, datetime

    assert module.price_day_query(date(2026, 10, 8)) == {
        "date": {"$gte": datetime(2026, 10, 8), "$lt": datetime(2026, 10, 9)}
    }


def test_liquidity_rows_are_restricted_to_the_as_of_day_and_window():
    from datetime import date, datetime

    class VolumeCollection:
        def __init__(self):
            self.query = None

        def find(self, query, projection=None):
            self.query = query
            return [
                {"symbol": "2330", "date": datetime(2026, 10, 8), "volume": 30_000_000},
                {"symbol": "2330", "date": datetime(2026, 10, 7), "volume": 20_000_000},
            ]

    collection = VolumeCollection()
    volumes = module.load_recent_volumes(collection, date(2026, 10, 8), ["2330"])

    assert volumes == {"2330": [30_000_000.0, 20_000_000.0]}
    assert collection.query["date"]["$lt"] == datetime(2026, 10, 9)
    assert collection.query["symbol"] == {"$in": ["2330"]}


def test_recent_trading_dates_come_from_price_history_not_the_calendar():
    from datetime import date, datetime

    class DateCollection:
        def distinct(self, field, query):
            assert field == "date"
            assert query["date"]["$lt"] == datetime(2026, 10, 10)
            return [datetime(2026, 10, 7), datetime(2026, 10, 9), datetime(2026, 10, 8)]

    assert module.recent_trading_dates(DateCollection(), date(2026, 10, 9), 2) == [
        date(2026, 10, 8),
        date(2026, 10, 9),
    ]


def test_lookback_captures_each_recent_trading_day(monkeypatch, capsys):
    from datetime import date

    seen = []

    class RecordingSource:
        name = "recording"

        def collect(self, as_of):
            seen.append(as_of)
            return SourceCollectionResult(self.name, [], "no_output")

    repository = FakeRepository(None)
    monkeypatch.setattr(module, "get_db", lambda: FakeDatabase())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda _: repository)
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [RecordingSource()])
    monkeypatch.setattr(
        module, "recent_trading_dates", lambda *_: [date(2026, 10, 8), date(2026, 10, 9)]
    )

    assert module.main(["--as-of", "2026-10-09", "--lookback", "2"]) == 0

    assert seen == [date(2026, 10, 8), date(2026, 10, 9)]


def test_dry_run_reports_counts_without_any_ledger_write(monkeypatch, capsys):
    constructed = []
    monkeypatch.setattr(module, "get_db", lambda: FakeDatabase())
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda db: constructed.append(db))
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [GoodSource()])

    assert module.main(["--as-of", "2026-10-10", "--dry-run"]) == 0

    assert constructed == []
    assert "good_source would_capture=1" in capsys.readouterr().out