"""TDD: 週五全市場批次延後完成，capture 必須主動納入尚在窗口內的 team 批次日。"""

from datetime import date, datetime

from scripts import capture_research_signals as module
from src.research_signal_ledger.sources.base import SourceCollectionResult


class TeamCollection:
    def __init__(self, dates):
        self.dates = dates
        self.query = None

    def distinct(self, field, query):
        assert field == "date"
        self.query = query
        return self.dates


def test_batch_dates_outside_the_trading_days_are_discovered():
    collection = TeamCollection([datetime(2026, 10, 2), datetime(2026, 10, 9), datetime(2026, 10, 12)])

    extra = module.extra_team_batch_dates(
        collection, date(2026, 10, 12), window_days=14, already={date(2026, 10, 12)}
    )

    assert extra == [date(2026, 10, 2), date(2026, 10, 9)]


def test_the_window_is_about_when_a_conclusion_finished_not_the_batch_day():
    collection = TeamCollection([])

    module.extra_team_batch_dates(collection, date(2026, 10, 12), window_days=14, already=set())

    # 只納入「最近才完成」的結論；帳本啟用前就完成的舊分析屬於歷史回補，不得被帶進來。
    assert collection.query["updated_at"] == {"$gte": datetime(2026, 9, 28)}
    assert collection.query["date"] == {"$lt": datetime(2026, 10, 13)}
    assert collection.query["final_verdict"] == {"$nin": [None, ""]}


def test_conclusions_finished_before_the_ledger_existed_are_never_pulled_in():
    collection = TeamCollection([])

    module.extra_team_batch_dates(
        collection, date(2026, 10, 12), 14, set(), not_before=datetime(2026, 10, 10, 21, 46)
    )

    assert collection.query["updated_at"] == {"$gte": datetime(2026, 10, 10, 21, 46)}


def test_a_zero_window_disables_discovery():
    assert module.extra_team_batch_dates(TeamCollection([datetime(2026, 10, 9)]), date(2026, 10, 12), 0, set()) == []


class Collections:
    def __init__(self, team_dates):
        self.team = TeamCollection(team_dates)

    def __getitem__(self, name):
        if name == "team_analysis":
            return self.team
        assert name == "stock_price"
        return self

    def find(self, query, projection=None):
        return []


class Repository:
    def __init__(self, database):
        self.runs = []

    def insert_snapshots(self, snapshots):
        raise AssertionError("no snapshots expected")

    def insert_benchmark(self, snapshot):
        return False

    def record_capture_run(self, run):
        self.runs.append(run)


class Recorder:
    def __init__(self, name, seen):
        self.name = name
        self.seen = seen

    def collect(self, as_of):
        self.seen.append((self.name, as_of))
        return SourceCollectionResult(self.name, [], "no_output")


def _run(monkeypatch, argv, team_dates):
    seen = []
    monkeypatch.setattr(module, "get_db", lambda: Collections(team_dates))
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", Repository)
    monkeypatch.setattr(
        module, "build_default_sources", lambda *_: [Recorder("team_analysis", seen), Recorder("risk", seen)]
    )
    monkeypatch.setattr(module, "recent_trading_dates", lambda *_: [date(2026, 10, 8), date(2026, 10, 12)])
    assert module.main(argv) == 0
    return seen


def test_extra_batch_days_run_only_the_team_source(monkeypatch):
    seen = _run(monkeypatch, ["--as-of", "2026-10-12", "--lookback", "2"], [datetime(2026, 10, 9)])

    assert ("team_analysis", date(2026, 10, 9)) in seen
    assert ("risk", date(2026, 10, 9)) not in seen
    assert ("risk", date(2026, 10, 12)) in seen


def test_a_single_day_capture_never_adds_extra_days(monkeypatch):
    seen = []
    monkeypatch.setattr(module, "get_db", lambda: Collections([datetime(2026, 10, 9)]))
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", Repository)
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [Recorder("team_analysis", seen)])

    assert module.main(["--as-of", "2026-10-12"]) == 0

    assert seen == [("team_analysis", date(2026, 10, 12))]


def test_source_option_restricts_capture_to_the_named_source(monkeypatch):
    seen = []
    monkeypatch.setattr(module, "get_db", lambda: Collections([]))
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", Repository)
    monkeypatch.setattr(
        module, "build_default_sources", lambda *_: [Recorder("team_analysis", seen), Recorder("risk", seen)]
    )

    assert module.main(["--as-of", "2026-09-25", "--source", "team_analysis"]) == 0

    assert seen == [("team_analysis", date(2026, 9, 25))]


def test_benchmark_only_runs_no_source_and_records_no_capture_run(monkeypatch):
    seen = []
    repository = []
    monkeypatch.setattr(module, "get_db", lambda: Collections([]))
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", lambda db: repository.append(Repository(db)) or repository[-1])
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [Recorder("team_analysis", seen)])

    assert module.main(["--as-of", "2026-09-24", "--benchmark-only"]) == 0

    assert seen == []
    assert repository[0].runs == []


def test_an_unknown_source_name_is_rejected(monkeypatch):
    monkeypatch.setattr(module, "get_db", lambda: Collections([]))
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [Recorder("risk", [])])

    try:
        module.main(["--as-of", "2026-09-25", "--source", "nope", "--dry-run"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("expected SystemExit")


def test_the_window_can_be_disabled_from_the_cli(monkeypatch):
    seen = _run(monkeypatch, ["--as-of", "2026-10-12", "--lookback", "2", "--team-window-days", "0"], [datetime(2026, 10, 9)])

    assert all(day != date(2026, 10, 9) for _, day in seen)
