"""TDD: 研究訊號來源必須正規化或明確回報沒有輸出。"""

import json
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.research_signal_ledger.models import SignalDirection
from src.research_signal_ledger.sources import build_default_sources
from src.research_signal_ledger.sources.base import build_snapshot_key
from src.research_signal_ledger.sources.daily_picks import DailyPicksSource
from src.research_signal_ledger.sources.on_demand import OnDemandSource
from src.research_signal_ledger.sources.team_analysis import TeamAnalysisSource
from src.research_signal_ledger.sources.technical import TechnicalSource


pytestmark = pytest.mark.unit


def test_daily_picks_emits_one_snapshot_per_symbol_and_strategy(tmp_path):
    (tmp_path / "picks_20261010_210000.json").write_text(
        json.dumps(
            {
                "date": "2026-10-10T21:00:00+00:00",
                "factor": [{"sym": "2330", "price": 100.0, "total_score": 83.0}],
                "hsieh": [{"sym": "2330", "price": 100.0, "dy": 4.2}],
                "senvision": [],
            }
        ),
        encoding="utf-8",
    )

    result = DailyPicksSource(tmp_path).collect(date(2026, 10, 10))

    assert result.status == "captured"
    assert {(snapshot.symbol, snapshot.signal_kind) for snapshot in result.snapshots} == {
        ("2330", "factor_rank"),
        ("2330", "hsieh_value"),
    }


def test_missing_on_demand_output_is_not_a_capture_failure():
    result = OnDemandSource().collect(date(2026, 10, 10))

    assert result.status == "no_output"
    assert result.snapshots == []


def test_changed_rule_version_creates_a_distinct_snapshot_key():
    common = {
        "source": "daily_picks",
        "source_event_id": "sha256:report:2026-10-10",
        "symbol": "2330",
        "analysis_date": date(2026, 10, 10),
        "signal_kind": "factor_rank",
        "direction": SignalDirection.LONG,
    }

    first = build_snapshot_key(**common, rule_version="daily_picks_v1")
    second = build_snapshot_key(**common, rule_version="daily_picks_v2")

    assert first != second


def test_daily_picks_rejects_latest_as_a_source_event_id(tmp_path):
    (tmp_path / "picks_20261010_210000.json").write_text(
        json.dumps(
            {
                "date": "2026-10-10T21:00:00+00:00",
                "factor": [{"sym": "2330", "price": 100.0}],
            }
        ),
        encoding="utf-8",
    )

    source = DailyPicksSource(tmp_path)
    with pytest.raises(ValidationError):
        source._normalize_row(
            {"sym": "2330", "price": 100.0},
            "factor_rank",
            date(2026, 10, 10),
            source._report_time("2026-10-10T21:00:00+00:00", date(2026, 10, 10)),
            "latest",
        )


class FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, query):
        return self.documents


class FakeDatabase:
    def __init__(self, **collections):
        self.collections = collections

    def __getitem__(self, name):
        return self.collections[name]


def test_team_analysis_maps_buy_verdict_to_evaluable_long_snapshot():
    database = FakeDatabase(
        team_analysis=FakeCollection(
            [
                {
                    "_id": "team-2330-20261010",
                    "symbol": "2330",
                    "date": "2026-10-10",
                    "final_verdict": "買進",
                    "price_at_analysis": 100.0,
                    "updated_at": datetime(2026, 10, 10, 20, 0),
                    "models": {"fundamental": "model-a"},
                    "consensus": {"tally": {"買進": 4}},
                }
            ]
        )
    )

    result = TeamAnalysisSource(database).collect(date(2026, 10, 10))

    assert result.status == "captured"
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.direction is SignalDirection.LONG
    assert snapshot.evaluation_enabled is True
    assert snapshot.source_payload == {
        "final_verdict": "買進",
        "models": {"fundamental": "model-a"},
        "consensus_tally": {"買進": 4},
    }


def _write_screen(tmp_path, rows, data_date="2026-10-08"):
    (tmp_path / f"research_screen_{data_date}.json").write_text(
        json.dumps({"data_date": data_date, "rows": rows}, ensure_ascii=False), encoding="utf-8"
    )


def _write_csv(path, header, rows):
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_chip_csv_maps_verdicts_to_directions_and_skips_neutral(tmp_path):
    from src.research_signal_ledger.sources.csv_scans import build_csv_sources

    _write_csv(
        tmp_path / "chip" / "chip_scan_20261008.csv",
        ["代碼", "收盤", "研判"],
        [
            ["2330", "100", "主力吸籌·散戶退"],
            ["2317", "50", "主力出貨·散戶接"],
            ["1101", "40", "中性/不明顯"],
            ["2454", "300", "沒看過的新類別"],
        ],
    )
    source = {s.name: s for s in build_csv_sources(tmp_path)}["chip"]

    snapshots = {s.symbol: s for s in source.collect(date(2026, 10, 8)).snapshots}

    assert set(snapshots) == {"2330", "2317"}
    assert snapshots["2330"].direction is SignalDirection.LONG
    assert snapshots["2317"].direction is SignalDirection.RISK_REDUCE
    assert all(snapshot.evaluation_enabled for snapshot in snapshots.values())


def test_csv_source_tolerates_stray_spaces_in_headers(tmp_path):
    from src.research_signal_ledger.sources.csv_scans import build_csv_sources

    _write_csv(
        tmp_path / "volume_price" / "vp_scan_20261008.csv",
        ["代碼", "收盤", "分 類"],
        [["6199", "142.0", "爆量突破"]],
    )
    source = {s.name: s for s in build_csv_sources(tmp_path)}["volume_price"]

    snapshots = source.collect(date(2026, 10, 8)).snapshots

    assert [(s.symbol, s.signal_kind) for s in snapshots] == [("6199", "volume_price_class")]


def test_csv_source_without_a_dated_file_is_no_output(tmp_path):
    from src.research_signal_ledger.sources.csv_scans import build_csv_sources

    for source in build_csv_sources(tmp_path):
        assert source.collect(date(2026, 10, 8)).status == "no_output"


def test_research_screen_marks_green_as_evaluable_long_and_yellow_as_observe(tmp_path):
    from src.research_signal_ledger.sources.research_screen import ResearchScreenSource

    _write_screen(
        tmp_path,
        [
            {"tier": "🟢", "symbol": "4736", "score": 81.7},
            {"tier": "🟡", "symbol": "2330", "score": 60.0},
        ],
    )

    result = ResearchScreenSource(tmp_path, lambda symbols, day: {"4736": 50.0, "2330": 100.0}).collect(
        date(2026, 10, 8)
    )

    by_symbol = {snapshot.symbol: snapshot for snapshot in result.snapshots}
    assert result.status == "captured"
    assert (by_symbol["4736"].direction, by_symbol["4736"].evaluation_enabled) == (SignalDirection.LONG, True)
    assert (by_symbol["2330"].direction, by_symbol["2330"].evaluation_enabled) == (
        SignalDirection.OBSERVE,
        False,
    )


def test_research_screen_skips_rows_without_a_reference_price(tmp_path):
    from src.research_signal_ledger.sources.research_screen import ResearchScreenSource

    _write_screen(tmp_path, [{"tier": "🟢", "symbol": "4736", "score": 81.7}])

    result = ResearchScreenSource(tmp_path, lambda symbols, day: {}).collect(date(2026, 10, 8))

    assert result.snapshots == []
    assert result.status == "no_output"


def test_research_screen_without_a_file_for_the_day_is_no_output(tmp_path):
    from src.research_signal_ledger.sources.research_screen import ResearchScreenSource

    result = ResearchScreenSource(tmp_path, lambda symbols, day: {}).collect(date(2026, 10, 8))

    assert result.status == "no_output"


def test_daily_picks_treats_naive_report_time_as_taipei_local_time(tmp_path):
    from datetime import datetime, timedelta, timezone

    (tmp_path / "picks_20261008_204422.json").write_text(
        json.dumps({"date": "2026-10-08T20:44:22.250071", "factor": [{"sym": "2330", "price": 100.0}]}),
        encoding="utf-8",
    )

    snapshot = DailyPicksSource(tmp_path).collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.available_at == datetime(
        2026, 10, 8, 20, 44, 22, 250071, tzinfo=timezone(timedelta(hours=8))
    )


def test_team_analysis_treats_naive_mongo_time_as_taipei_local_time():
    from datetime import datetime, timedelta, timezone

    database = FakeDatabase(
        team_analysis=FakeCollection(
            [
                {
                    "_id": "team-2330",
                    "symbol": "2330",
                    "date": datetime(2026, 10, 8),
                    "final_verdict": "買進",
                    "price_at_analysis": 100.0,
                    "updated_at": datetime(2026, 10, 8, 20, 47, 38),
                }
            ]
        )
    )

    snapshot = TeamAnalysisSource(database).collect(date(2026, 10, 8)).snapshots[0]

    assert snapshot.available_at == datetime(
        2026, 10, 8, 20, 47, 38, tzinfo=timezone(timedelta(hours=8))
    )


def test_vcp_candidates_map_to_evaluable_technical_snapshots():
    database = FakeDatabase(
        vcp_candidates=FakeCollection(
            [
                {
                    "_id": "vcp-2330-20261010",
                    "scan_date": "2026-10-10",
                    "symbol": "2330",
                    "price": 100.0,
                    "score": 82.0,
                    "pivot": 105.0,
                    "near_pivot": True,
                }
            ]
        )
    )

    result = TechnicalSource(database).collect(date(2026, 10, 10))

    assert result.status == "captured"
    assert [(snapshot.symbol, snapshot.signal_kind) for snapshot in result.snapshots] == [
        ("2330", "vcp")
    ]
    assert result.snapshots[0].direction is SignalDirection.LONG


def test_default_registry_reports_unavailable_source_groups_explicitly(tmp_path):
    database = FakeDatabase(
        team_analysis=FakeCollection([]),
        vcp_candidates=FakeCollection([]),
        risk_analysis=FakeCollection([]),
        stock_price=FakeCollection([]),
    )

    results = {
        result.source: result.status
        for source in build_default_sources(database, tmp_path)
        for result in [source.collect(date(2026, 10, 10))]
    }

    assert results["daily_picks"] == "no_output"
    assert results["research_screen"] == "no_output"
    assert results["team_analysis"] == "no_output"
    assert results["technical"] == "no_output"
    assert results["core_watchlist"] == "no_output"
    assert results["obv_bottom"] == "no_output"
    assert results["chip"] == "no_output"
    assert results["dual_signal"] == "no_output"
    assert results["volume_price"] == "no_output"
    assert results["risk"] == "no_output"
    assert results["on_demand"] == "no_output"


def test_research_screen_skips_the_price_lookup_for_an_empty_screen(tmp_path):
    from src.research_signal_ledger.sources.research_screen import ResearchScreenSource

    _write_screen(tmp_path, [])

    def forbidden_lookup(symbols, day):
        raise AssertionError("price lookup must be skipped when there are no rows")

    result = ResearchScreenSource(tmp_path, forbidden_lookup).collect(date(2026, 10, 8))

    assert result.status == "no_output"