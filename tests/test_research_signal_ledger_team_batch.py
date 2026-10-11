"""TDD: team_analysis 的可用時間與完成度（週五全市場批次延後約 5 天才完成）。"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.research_signal_ledger.models import SignalDirection
from src.research_signal_ledger.sources.team_analysis import TeamAnalysisSource


pytestmark = pytest.mark.unit

TAIPEI = timezone(timedelta(hours=8))


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(query)
        return self.documents


class Database:
    def __init__(self, documents):
        self.collection = Collection(documents)

    def __getitem__(self, name):
        return self.collection


def doc(symbol="2330", verdict="買進", updated_at=datetime(2026, 10, 14, 7, 48, 1), **extra):
    return {
        "_id": f"t-{symbol}",
        "symbol": symbol,
        "date": datetime(2026, 10, 9),
        "final_verdict": verdict,
        "price_at_analysis": 100.0,
        "updated_at": updated_at,
    } | extra


def collect(documents, day=date(2026, 10, 9)):
    return TeamAnalysisSource(Database(documents)).collect(day)


def test_available_at_is_the_completion_time_not_the_batch_day():
    snapshot = collect([doc()]).snapshots[0]

    assert snapshot.analysis_date == date(2026, 10, 9)
    assert snapshot.available_at == datetime(2026, 10, 14, 7, 48, 1, tzinfo=TAIPEI)


def test_an_unfinished_deliberation_is_not_a_signal_yet():
    result = collect([doc("2330", None), doc("2317", ""), doc("2454", "買進")])

    assert [s.symbol for s in result.snapshots] == ["2454"]


def test_a_document_without_a_completion_time_is_skipped_instead_of_assumed_available():
    result = collect([doc("2330", updated_at=None), doc("2317")])

    assert [s.symbol for s in result.snapshots] == ["2317"]


def test_sell_and_trim_verdicts_are_risk_reduce_and_buy_verdicts_are_long():
    result = collect([doc("1101", "賣出"), doc("1102", "減碼"), doc("1103", "強力買進"), doc("1104", "持有")])
    by_symbol = {s.symbol: s for s in result.snapshots}

    assert by_symbol["1101"].direction is SignalDirection.RISK_REDUCE
    assert by_symbol["1102"].direction is SignalDirection.RISK_REDUCE
    assert by_symbol["1103"].direction is SignalDirection.LONG
    assert by_symbol["1104"].evaluation_enabled is False


def test_the_query_is_bounded_to_the_analysis_day():
    database = Database([])
    TeamAnalysisSource(database).collect(date(2026, 10, 9))

    assert database.collection.queries == [
        {"date": {"$gte": datetime(2026, 10, 9), "$lt": datetime(2026, 10, 10)}}
    ]


def test_a_batch_with_nothing_finished_is_no_output():
    assert collect([doc("2330", None)]).status == "no_output"
