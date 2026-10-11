"""TDD: 持倉風控與上游落地來源的正規化。"""

from datetime import date, datetime, timedelta, timezone

import pytest

from src.research_signal_ledger.models import SignalDirection
from src.research_signal_ledger.sources.risk import RiskAnalysisSource


pytestmark = pytest.mark.unit

TAIPEI = timezone(timedelta(hours=8))


class QueryRecordingCollection:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find(self, query, projection=None):
        self.queries.append(query)
        return self.documents


class FakeDatabase:
    def __init__(self, **collections):
        self.collections = collections

    def __getitem__(self, name):
        return self.collections[name]


def _risk_doc(symbol="2603", verdict="減碼", **overrides):
    return {
        "_id": f"risk-{symbol}",
        "date": datetime(2026, 10, 8),
        "symbol": symbol,
        "verdict": verdict,
        "tally": {"續抱": 1, "減碼": 3, "出場": 1},
        "reason": "跌破月線",
        "rules": "hold",
        "updated_at": datetime(2026, 10, 8, 20, 29, 19),
    } | overrides


def _source(documents, prices):
    database = FakeDatabase(risk_analysis=QueryRecordingCollection(documents))
    return RiskAnalysisSource(database, lambda symbols, day: prices)


def test_trim_and_exit_are_evaluable_risk_reduce_signals():
    source = _source([_risk_doc("2603", "減碼"), _risk_doc("2330", "出場")], {"2603": 80.0, "2330": 900.0})

    snapshots = {s.symbol: s for s in source.collect(date(2026, 10, 8)).snapshots}

    assert set(snapshots) == {"2603", "2330"}
    assert all(s.direction is SignalDirection.RISK_REDUCE for s in snapshots.values())
    assert all(s.evaluation_enabled for s in snapshots.values())
    assert snapshots["2603"].price_at_signal == 80.0


def test_keep_holding_is_recorded_but_never_evaluated():
    source = _source([_risk_doc("2603", "續抱")], {"2603": 80.0})

    snapshot = source.collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.direction is SignalDirection.HOLD
    assert snapshot.evaluation_enabled is False


def test_risk_signal_becomes_available_at_the_document_write_time_in_taipei_time():
    source = _source([_risk_doc()], {"2603": 80.0})

    snapshot = source.collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.available_at == datetime(2026, 10, 8, 20, 29, 19, tzinfo=TAIPEI)


def test_position_without_a_reference_price_is_skipped_not_zero_filled():
    source = _source([_risk_doc("2603", "減碼")], {})

    result = source.collect(date(2026, 10, 8))

    assert result.snapshots == []
    assert result.status == "no_output"


def test_unknown_verdict_produces_no_snapshot():
    source = _source([_risk_doc("2603", "未知判斷")], {"2603": 80.0})

    assert source.collect(date(2026, 10, 8)).snapshots == []


def test_risk_query_is_bounded_to_the_requested_day():
    collection = QueryRecordingCollection([])
    RiskAnalysisSource(FakeDatabase(risk_analysis=collection), lambda s, d: {}).collect(date(2026, 10, 8))

    assert collection.queries == [
        {"date": {"$gte": datetime(2026, 10, 8), "$lt": datetime(2026, 10, 9)}}
    ]


def test_same_content_rerun_yields_the_same_snapshot_key():
    first = _source([_risk_doc()], {"2603": 80.0}).collect(date(2026, 10, 8)).snapshots[0]
    second = _source([_risk_doc()], {"2603": 80.0}).collect(date(2026, 10, 8)).snapshots[0]

    assert first.snapshot_key == second.snapshot_key


def test_changed_verdict_in_a_same_day_rerun_is_a_distinct_snapshot():
    first = _source([_risk_doc(verdict="減碼")], {"2603": 80.0}).collect(date(2026, 10, 8)).snapshots[0]
    second = _source([_risk_doc(verdict="出場")], {"2603": 80.0}).collect(date(2026, 10, 8)).snapshots[0]

    assert first.snapshot_key != second.snapshot_key


def test_no_price_lookup_is_made_when_there_are_no_candidates():
    def forbidden_lookup(symbols, day):
        raise AssertionError("price lookup must be skipped when nothing needs a price")

    source = RiskAnalysisSource(FakeDatabase(risk_analysis=QueryRecordingCollection([])), forbidden_lookup)

    assert source.collect(date(2026, 10, 8)).status == "no_output"


def test_an_etf_holding_is_skipped_without_losing_the_other_positions():
    source = _source(
        [_risk_doc("00919", "減碼"), _risk_doc("2603", "減碼")],
        {"00919": 22.0, "2603": 80.0},
    )

    result = source.collect(date(2026, 10, 8))

    assert result.status == "captured"
    assert [snapshot.symbol for snapshot in result.snapshots] == ["2603"]
    assert "skipped=1" in (result.message or "")


def test_a_position_that_fails_validation_does_not_discard_the_rest():
    source = _source(
        [_risk_doc("ABCD", "減碼"), _risk_doc("2330", "出場")],
        {"ABCD": 10.0, "2330": 900.0},
    )

    result = source.collect(date(2026, 10, 8))

    assert [snapshot.symbol for snapshot in result.snapshots] == ["2330"]
    assert "skipped=1" in (result.message or "")


def _write_signal_file(tmp_path, name, rows, suffix="", data_date="2026-10-08"):
    import json

    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}_20261008{suffix}.json").write_text(
        json.dumps({"data_date": data_date, "rows": rows}, ensure_ascii=False), encoding="utf-8"
    )


def test_obv_bottom_signals_are_evaluable_long_snapshots(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    _write_signal_file(tmp_path, "obv_bottom", [{"symbol": "2548", "close": 91.8, "pattern": "W-Bottom"}])
    source = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {})}["obv_bottom"]

    snapshot = source.collect(date(2026, 10, 8)).snapshots[0]

    assert (snapshot.symbol, snapshot.direction, snapshot.evaluation_enabled) == (
        "2548", SignalDirection.LONG, True,
    )
    assert snapshot.price_at_signal == 91.8


def test_core_signals_map_entry_to_long_and_warn_to_risk_reduce(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    _write_signal_file(
        tmp_path,
        "core_signals",
        [
            {"symbol": "2330", "entry": ["2560做量"], "warn": []},
            {"symbol": "2317", "entry": [], "warn": ["月線高位放量"]},
        ],
    )
    source = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {"2330": 900.0, "2317": 100.0})}[
        "core_watchlist"
    ]

    snapshots = {s.symbol: s for s in source.collect(date(2026, 10, 8)).snapshots}

    assert snapshots["2330"].direction is SignalDirection.LONG
    assert snapshots["2317"].direction is SignalDirection.RISK_REDUCE


def test_a_stock_with_both_entry_and_warn_yields_two_signals(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    _write_signal_file(tmp_path, "core_signals", [{"symbol": "2330", "entry": ["反彈潛力高"], "warn": ["月線高位放量"]}])
    source = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {"2330": 900.0})}["core_watchlist"]

    directions = sorted(s.direction.value for s in source.collect(date(2026, 10, 8)).snapshots)

    assert directions == ["long", "risk_reduce"]


def test_the_highest_numbered_rerun_file_is_the_one_that_is_read(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    _write_signal_file(tmp_path, "obv_bottom", [{"symbol": "2548", "close": 91.8}])
    _write_signal_file(tmp_path, "obv_bottom", [{"symbol": "6177", "close": 45.9}], suffix=".2")
    source = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {})}["obv_bottom"]

    assert [s.symbol for s in source.collect(date(2026, 10, 8)).snapshots] == ["6177"]


def test_a_missing_upstream_file_is_no_output(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    for source in build_upstream_sources(tmp_path, lambda symbols, day: {}):
        assert source.collect(date(2026, 10, 8)).status == "no_output"


def test_an_empty_signal_file_is_no_output_not_a_failure(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    _write_signal_file(tmp_path, "obv_bottom", [])
    source = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {})}["obv_bottom"]

    assert source.collect(date(2026, 10, 8)).status == "no_output"


def test_fundamental_screens_become_long_snapshots_using_the_file_price(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    for directory in ("hsieh_growth", "quality_growth", "agan_moat"):
        _write_signal_file(
            tmp_path, directory, [{"symbol": "2330", "name": "台積電", "price": 900.0, "roe": 25.0}]
        )
    sources = {s.name: s for s in build_upstream_sources(tmp_path, lambda symbols, day: {})}

    for name in ("hsieh_growth", "quality_growth", "agan_moat"):
        snapshot = sources[name].collect(date(2026, 10, 8)).snapshots[0]
        assert (snapshot.symbol, snapshot.direction, snapshot.price_at_signal) == (
            "2330", SignalDirection.LONG, 900.0,
        )
        assert snapshot.evaluation_enabled is True


def test_fundamental_screens_are_distinct_methods_with_distinct_signal_kinds(tmp_path):
    from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources

    for directory in ("hsieh_growth", "quality_growth", "agan_moat"):
        _write_signal_file(tmp_path, directory, [{"symbol": "2330", "price": 900.0}])
    sources = build_upstream_sources(tmp_path, lambda symbols, day: {})

    kinds = {s.name: s.collect(date(2026, 10, 8)).snapshots[0].signal_kind for s in sources
             if s.name in ("hsieh_growth", "quality_growth", "agan_moat")}

    assert len(set(kinds.values())) == 3


def test_team_snapshots_keep_the_news_evidence_so_news_value_can_be_re_cut_later():
    from src.research_signal_ledger.sources.team_analysis import TeamAnalysisSource

    class Collection:
        def find(self, query):
            return [
                {
                    "_id": "t1", "symbol": "2330", "date": "2026-10-08", "final_verdict": "買進",
                    "price_at_analysis": 100.0, "updated_at": datetime(2026, 10, 8, 20, 0),
                    "catalyst": True, "news_count": 3,
                    "news_official": True, "news_media": False,
                }
            ]

    class Database:
        def __getitem__(self, name):
            return Collection()

    snapshot = TeamAnalysisSource(Database()).collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.source_payload["catalyst"] is True
    assert snapshot.source_payload["news_count"] == 3
    assert snapshot.source_payload["news_official"] is True


def test_team_snapshots_without_news_fields_still_capture():
    from src.research_signal_ledger.sources.team_analysis import TeamAnalysisSource

    class Collection:
        def find(self, query):
            return [{"_id": "t1", "symbol": "2330", "date": "2026-10-08", "final_verdict": "買進", "price_at_analysis": 100.0, "updated_at": datetime(2026, 10, 8, 20, 0)}]

    class Database:
        def __getitem__(self, name):
            return Collection()

    snapshot = TeamAnalysisSource(Database()).collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.source_payload.get("catalyst") is None
