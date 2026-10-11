"""研究訊號的成熟績效評估純函式。"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Iterable

from src.backtesting.tw_costs import roundtrip_pct
from src.research_signal_ledger.models import (
    ResearchBenchmarkSnapshot,
    ResearchSignalOutcome,
    ResearchSignalSnapshot,
    SignalDirection,
)


@dataclass(frozen=True)
class TradingPrice:
    symbol: str
    date: date
    adj_close: float


MIN_BENCHMARK_COVERAGE = 0.95


def _gross_return_pct(direction: SignalDirection, entry: float, exit: float) -> float:
    if direction in (SignalDirection.SHORT, SignalDirection.RISK_REDUCE):
        return (entry / exit - 1) * 100
    return (exit / entry - 1) * 100


def _price_map(rows: Iterable[TradingPrice]) -> dict[str, dict[date, float]]:
    prices: dict[str, dict[date, float]] = defaultdict(dict)
    for row in rows:
        if row.adj_close > 0:
            prices[row.symbol][row.date] = row.adj_close
    return prices


def evaluate_snapshot(
    snapshot: ResearchSignalSnapshot,
    benchmark: ResearchBenchmarkSnapshot,
    prices: Iterable[TradingPrice],
    horizons: tuple[int, ...] = (5, 10, 20),
    discount: float = 1.0,
) -> list[ResearchSignalOutcome]:
    """以可用後首個交易日進場，產生已成熟 horizon 的 append-only outcome。"""
    if not snapshot.evaluation_enabled:
        return []

    price_by_symbol = _price_map(prices)
    signal_prices = sorted(
        (
            TradingPrice(snapshot.symbol, trading_date, adj_close)
            for trading_date, adj_close in price_by_symbol.get(snapshot.symbol, {}).items()
            if trading_date > snapshot.available_at.date()
        ),
        key=lambda row: row.date,
    )
    if not signal_prices:
        return []

    outcomes: list[ResearchSignalOutcome] = []
    entry = signal_prices[0]
    for horizon in horizons:
        if horizon not in (5, 10, 20) or len(signal_prices) <= horizon:
            continue
        exit = signal_prices[horizon]
        benchmark_returns: list[float] = []
        for symbol in benchmark.symbols:
            entry_price = price_by_symbol.get(symbol, {}).get(entry.date)
            exit_price = price_by_symbol.get(symbol, {}).get(exit.date)
            if entry_price is None or exit_price is None:
                continue  # 停牌/無資料的成員不計入；覆蓋率不足才放棄整個 horizon。
            benchmark_returns.append(
                _gross_return_pct(snapshot.direction, entry_price, exit_price)
            )
        if len(benchmark_returns) < len(benchmark.symbols) * MIN_BENCHMARK_COVERAGE:
            continue

        gross_return_pct = _gross_return_pct(snapshot.direction, entry.adj_close, exit.adj_close)
        has_trade_cost = snapshot.direction not in (SignalDirection.HOLD, SignalDirection.OBSERVE)
        cost_pct = roundtrip_pct(discount) if has_trade_cost else 0.0
        net_return_pct = gross_return_pct - cost_pct
        excess_mkt_pct = gross_return_pct - (sum(benchmark_returns) / len(benchmark_returns))
        hit = (
            None
            if snapshot.direction in (SignalDirection.HOLD, SignalDirection.OBSERVE)
            else net_return_pct > 0 and excess_mkt_pct > 0
        )
        outcomes.append(
            ResearchSignalOutcome(
                outcome_key=f"{snapshot.snapshot_key}:{horizon}:1",
                snapshot_key=snapshot.snapshot_key,
                horizon_trading_days=horizon,
                revision=1,
                entry_date=entry.date,
                exit_date=exit.date,
                entry_adj_close=entry.adj_close,
                exit_adj_close=exit.adj_close,
                direction=snapshot.direction,
                gross_return_pct=gross_return_pct,
                net_return_pct=net_return_pct,
                excess_mkt_pct=excess_mkt_pct,
                excess_pool_pct=None,
                hit=hit,
                cost_pct=cost_pct,
                price_data_as_of=datetime.combine(exit.date, time.min, tzinfo=UTC),
                evaluated_at=datetime.now(UTC),
            )
        )
    return outcomes