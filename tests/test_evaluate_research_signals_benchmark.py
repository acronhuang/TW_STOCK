"""TDD: 評估器必須能為所有來源找到市場基準，包含休市日與 team 的 analysis_pool_v1 宣告。"""

from datetime import date, datetime, timezone

import pytest

from scripts import evaluate_research_signals as module
from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection


pytestmark = pytest.mark.unit

MARKET = "market_equal_weight_liquid_tw_v1"


class Benchmarks:
    def __init__(self, documents):
        self.documents = documents
        self.queries = []

    def find_one(self, query, sort=None):
        self.queries.append(query)
        matches = []
        for document in self.documents:
            if document["profile"] != query["profile"]:
                continue
            bound = query["analysis_date"]
            if not (bound["$gte"] <= document["analysis_date"] <= bound["$lte"]):
                continue
            matches.append(document)
        if sort:
            field, direction = sort[0]
            matches.sort(key=lambda d: d[field], reverse=direction < 0)
        return dict(matches[0]) if matches else None


class Repository:
    def __init__(self, documents):
        self.benchmarks = Benchmarks(documents)


def benchmark_doc(day, profile=MARKET):
    return {
        "benchmark_key": f"{profile}:{day}",
        "profile": profile,
        "analysis_date": day,
        "symbol_count": 1,
        "symbols": ["2330"],
        "membership_hash": "a" * 64,
        "captured_at": datetime(2026, 10, 10, tzinfo=timezone.utc).isoformat(),
    }


def snapshot(day, profile="analysis_pool_v1"):
    return ResearchSignalSnapshot(
        snapshot_key="a" * 64,
        source="team_analysis",
        source_event_id="mongo:1:sha256:x",
        symbol="2330",
        analysis_date=day,
        available_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc),
        captured_at=datetime(2026, 10, 12, 11, tzinfo=timezone.utc),
        signal_kind="final_verdict",
        direction=SignalDirection.LONG,
        evaluation_enabled=True,
        price_at_signal=100.0,
        source_payload={},
        benchmark_profile=profile,
        rule_version="v1",
    )


def test_an_analysis_pool_snapshot_is_evaluated_against_the_market_benchmark():
    repository = Repository([benchmark_doc("2026-10-08")])

    benchmark = module._load_benchmark(repository, snapshot(date(2026, 10, 8)))

    assert benchmark is not None
    assert benchmark.profile == MARKET


def test_a_non_trading_analysis_day_uses_the_latest_earlier_benchmark():
    repository = Repository([benchmark_doc("2026-10-07"), benchmark_doc("2026-10-08")])

    benchmark = module._load_benchmark(repository, snapshot(date(2026, 10, 9)))

    assert benchmark.analysis_date == date(2026, 10, 8)


def test_a_benchmark_older_than_a_week_is_too_stale_to_use():
    repository = Repository([benchmark_doc("2026-09-20")])

    assert module._load_benchmark(repository, snapshot(date(2026, 10, 9))) is None


def test_a_later_benchmark_is_never_used_for_an_earlier_signal():
    repository = Repository([benchmark_doc("2026-10-09")])

    assert module._load_benchmark(repository, snapshot(date(2026, 10, 8))) is None
