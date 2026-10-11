"""TDD: 研究訊號以還原價與台股成本評估成熟結果。"""

from datetime import date, datetime, timezone

import pytest

from src.research_signal_ledger.evaluator import TradingPrice, evaluate_snapshot
from src.research_signal_ledger.models import (
    ResearchBenchmarkSnapshot,
    ResearchSignalSnapshot,
    SignalDirection,
)


pytestmark = pytest.mark.unit


@pytest.fixture
def snapshot():
    return ResearchSignalSnapshot(
        snapshot_key="a" * 64,
        source="daily_picks",
        source_event_id="sha256:abc:2026-10-10",
        symbol="2330",
        analysis_date=date(2026, 10, 10),
        available_at=datetime(2026, 10, 10, 20, tzinfo=timezone.utc),
        captured_at=datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
        signal_kind="factor_rank",
        direction=SignalDirection.LONG,
        evaluation_enabled=True,
        price_at_signal=100.0,
        source_payload={"rank": 1},
        benchmark_profile="market_equal_weight_liquid_tw_v1",
        rule_version="daily_picks_v1",
    )


@pytest.fixture
def benchmark():
    return ResearchBenchmarkSnapshot(
        benchmark_key="benchmark:2026-10-10",
        profile="market_equal_weight_liquid_tw_v1",
        analysis_date=date(2026, 10, 10),
        symbol_count=1,
        symbols=["2330"],
        membership_hash="b" * 64,
        captured_at=datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
    )


@pytest.fixture
def prices():
    return [
        TradingPrice("2330", date(2026, 10, 12), 101.0),
        TradingPrice("2330", date(2026, 10, 13), 103.0),
        TradingPrice("2330", date(2026, 10, 14), 105.0),
        TradingPrice("2330", date(2026, 10, 15), 107.0),
        TradingPrice("2330", date(2026, 10, 16), 109.0),
        TradingPrice("2330", date(2026, 10, 19), 111.0),
    ]


def test_long_outcome_uses_next_trade_day_adjusted_price_and_roundtrip_cost(
    snapshot, benchmark, prices
):
    outcomes = evaluate_snapshot(snapshot, benchmark, prices, horizons=(5,), discount=1.0)

    outcome = outcomes[0]
    assert outcome.entry_adj_close == 101.0
    assert outcome.exit_adj_close == 111.0
    assert outcome.gross_return_pct == pytest.approx((111 / 101 - 1) * 100)
    assert outcome.cost_pct == pytest.approx(0.585)
    assert outcome.net_return_pct == pytest.approx(outcome.gross_return_pct - 0.585)


def test_insufficient_trading_days_produces_no_outcome(snapshot, benchmark, prices):
    assert evaluate_snapshot(snapshot, benchmark, prices, horizons=(20,)) == []


def _wide_benchmark_and_prices(snapshot, missing):
    """20 檔等權 benchmark；成員 M00..M19 以 1000..1019 當代號，前 missing 檔缺出場價。"""
    symbols = [f"{1000 + index}" for index in range(20)]
    benchmark = ResearchBenchmarkSnapshot(
        benchmark_key="wide",
        profile="market_equal_weight_liquid_tw_v1",
        analysis_date=date(2026, 10, 10),
        symbol_count=20,
        symbols=symbols,
        membership_hash="c" * 64,
        captured_at=datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
    )
    days = [date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14),
            date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 19)]
    prices = [TradingPrice("2330", d, p) for d, p in zip(days, [100, 101, 102, 103, 104, 110])]
    for index, symbol in enumerate(symbols):
        for position, day in enumerate(days):
            if position == 5 and index < missing:
                continue
            prices.append(TradingPrice(symbol, day, 100.0 if position < 5 else 101.0))
    return benchmark, prices


def test_benchmark_uses_members_with_prices_when_coverage_is_high_enough(snapshot):
    benchmark, prices = _wide_benchmark_and_prices(snapshot, missing=1)

    outcome = evaluate_snapshot(snapshot, benchmark, prices, horizons=(5,))[0]

    # 2330: 100 -> 110 = +10%；基準成員 100 -> 101 = +1%，缺價者被排除而非整個放棄。
    assert outcome.excess_mkt_pct == pytest.approx(9.0)


def test_benchmark_is_abandoned_when_too_many_members_lack_prices(snapshot):
    benchmark, prices = _wide_benchmark_and_prices(snapshot, missing=2)

    assert evaluate_snapshot(snapshot, benchmark, prices, horizons=(5,)) == []


def test_liquid_universe_keeps_only_four_digit_symbols_with_enough_average_volume():
    from src.research_signal_ledger.benchmark import select_liquid_symbols

    volume_by_symbol = {
        "2330": [30_000_000] * 20,
        "2317": [400_000] * 20,
        "1101": [200_000] * 20,
        "TAIEX": [900_000_000] * 20,
        "006208": [900_000_000] * 20,
        "03001P": [900_000_000] * 20,
        "5483": [],
    }

    assert select_liquid_symbols(volume_by_symbol) == ["2317", "2330"]


def test_liquid_universe_excludes_leading_zero_etfs():
    from src.research_signal_ledger.benchmark import select_liquid_symbols

    heavy = [30_000_000] * 20

    assert select_liquid_symbols({"0050": heavy, "0056": heavy, "2330": heavy}) == ["2330"]


def test_liquid_universe_requires_a_full_twenty_day_window():
    from src.research_signal_ledger.benchmark import select_liquid_symbols

    assert select_liquid_symbols({"2330": [30_000_000] * 19}) == []