#!/usr/bin/env python3
"""評估研究訊號已成熟的 5/10/20 交易日成本後 outcome。"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE  # noqa: E402
from src.research_signal_ledger.evaluator import TradingPrice, evaluate_snapshot  # noqa: E402
from src.research_signal_ledger.models import ResearchBenchmarkSnapshot, ResearchSignalSnapshot  # noqa: E402
from src.research_signal_ledger.repository import ResearchSignalLedgerRepository  # noqa: E402


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(int(part) for part in value.split(","))
    if not horizons or any(horizon not in (5, 10, 20) for horizon in horizons):
        raise argparse.ArgumentTypeError("horizons must be a comma-separated subset of 5,10,20")
    return horizons


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if hasattr(value, "to_decimal"):
        return float(value.to_decimal())
    return float(value) if isinstance(value, (int, float)) else None


def load_eligible_snapshots(repository: ResearchSignalLedgerRepository, as_of: date) -> list[ResearchSignalSnapshot]:
    snapshots = []
    for document in repository.snapshots.find({"evaluation_enabled": True}):
        document.pop("_id", None)
        snapshot = ResearchSignalSnapshot.model_validate(document)
        if snapshot.analysis_date <= as_of:
            snapshots.append(snapshot)
    return snapshots


MARKET_BENCHMARK = "market_equal_weight_liquid_tw_v1"
# 休市日沒有同日基準，取最近一份；超過一週的成員名單太舊，富認為無基準。
BENCHMARK_MAX_AGE_DAYS = 7


def _load_benchmark(repository: ResearchSignalLedgerRepository, snapshot: ResearchSignalSnapshot):
    """outcome 欄位是 excess_mkt_pct，所以一律對市場基準計算，不依快照宣告的 profile（team 宣告的 analysis_pool_v1 從未被建立）。"""
    upper = snapshot.analysis_date
    lower = upper - timedelta(days=BENCHMARK_MAX_AGE_DAYS)
    document = repository.benchmarks.find_one(
        {"profile": MARKET_BENCHMARK, "analysis_date": {"$gte": lower.isoformat(), "$lte": upper.isoformat()}},
        sort=[("analysis_date", -1)],
    )
    if document is None:
        return None
    document.pop("_id", None)
    return ResearchBenchmarkSnapshot.model_validate(document)


def pending_horizons(
    repository: ResearchSignalLedgerRepository,
    snapshot: ResearchSignalSnapshot,
    horizons: tuple[int, ...],
    as_of: date,
) -> tuple[int, ...]:
    """尚無 outcome 且依日曆日粗估有可能成熟的 horizon；N 個交易日至少要 N 個日曆日。"""
    available = snapshot.available_at.date()
    return tuple(
        horizon
        for horizon in horizons
        if available + timedelta(days=horizon) <= as_of
        and repository.latest_outcome(snapshot.snapshot_key, horizon) is None
    )


def evaluate_snapshot_outcomes(
    repository: ResearchSignalLedgerRepository,
    database,
    snapshot: ResearchSignalSnapshot,
    horizons: tuple[int, ...],
    caches: dict | None = None,
):
    caches = caches if caches is not None else {}
    key = snapshot.analysis_date
    if key not in caches:
        caches[key] = _load_benchmark(repository, snapshot)
    benchmark = caches[key]
    if benchmark is None:
        return []
    # 價格只取可用日之後的窗口、只投影所需欄位；同一 benchmark 與起始日的快照共用。
    window_start = snapshot.available_at.date()
    price_key = (key, window_start)
    if price_key not in caches:
        start = datetime.combine(window_start, datetime.min.time())
        end = start + timedelta(days=max(horizons) * 2 + 10)
        rows = []
        query = {"symbol": {"$in": list(benchmark.symbols)}, "date": {"$gt": start, "$lt": end}}
        for document in database[COLL_STOCK_PRICE].find(query, {"symbol": 1, "date": 1, "adj_close": 1}):
            trading_date = _as_date(document.get("date"))
            adjusted_close = _as_float(document.get("adj_close"))
            if trading_date is not None and adjusted_close is not None:
                rows.append(TradingPrice(document["symbol"], trading_date, adjusted_close))
        caches[price_key] = rows
    rows = caches[price_key]
    if not any(row.symbol == snapshot.symbol for row in rows):
        return []
    return evaluate_snapshot(snapshot, benchmark, rows, horizons=horizons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=_parse_date, default=date.today())
    parser.add_argument("--horizons", type=_parse_horizons, default=(5, 10, 20))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    database = get_db()
    repository = ResearchSignalLedgerRepository(database)
    appended = 0
    would_append = 0
    unripe_or_unavailable = 0
    caches: dict = {}
    for snapshot in load_eligible_snapshots(repository, args.as_of):
        horizons = pending_horizons(repository, snapshot, args.horizons, args.as_of)
        if not horizons:
            continue
        outcomes = evaluate_snapshot_outcomes(repository, database, snapshot, horizons, caches)
        if not outcomes:
            unripe_or_unavailable += 1
            continue
        for outcome in outcomes:
            if args.dry_run:
                would_append += 1
            else:
                appended += int(repository.append_outcome(outcome))
    if args.dry_run:
        print(f"would_append={would_append} unripe_or_unavailable={unripe_or_unavailable}")
    else:
        print(f"outcomes_appended={appended} unripe_or_unavailable={unripe_or_unavailable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())