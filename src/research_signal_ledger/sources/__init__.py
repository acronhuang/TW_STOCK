"""研究訊號來源 adapter。"""

from datetime import date, datetime, time, timedelta
from pathlib import Path

from src.domain.collections import COLL_STOCK_PRICE
from src.research_signal_ledger.sources.base import SignalSource, SourceCollectionResult
from src.research_signal_ledger.sources.csv_scans import build_csv_sources
from src.research_signal_ledger.sources.daily_picks import DailyPicksSource
from src.research_signal_ledger.sources.on_demand import OnDemandSource
from src.research_signal_ledger.sources.research_screen import ResearchScreenSource
from src.research_signal_ledger.sources.risk import RiskAnalysisSource
from src.research_signal_ledger.sources.team_analysis import TeamAnalysisSource
from src.research_signal_ledger.sources.technical import TechnicalSource
from src.research_signal_ledger.sources.unavailable import UnsupportedSource
from src.research_signal_ledger.sources.upstream_signals import build_upstream_sources


def _close_price_lookup(database):
    def lookup(symbols: list[str], day: date) -> dict[str, float]:
        if not symbols:
            return {}
        start = datetime.combine(day, time.min)
        query = {"symbol": {"$in": symbols}, "date": {"$gte": start, "$lt": start + timedelta(days=1)}}
        prices = {}
        for document in database[COLL_STOCK_PRICE].find(query, {"symbol": 1, "close": 1}):
            close = document.get("close")
            value = float(close.to_decimal()) if hasattr(close, "to_decimal") else close
            if isinstance(value, (int, float)):
                prices[document["symbol"]] = float(value)
        return prices

    return lookup


def build_default_sources(database, results_dir: Path):
    """回傳所有 V1 來源，未安全接通者也必須留下明確 capture 狀態。"""
    close_price_lookup = _close_price_lookup(database)
    return [
        DailyPicksSource(results_dir / "daily_picks"),
        ResearchScreenSource(results_dir, close_price_lookup),
        TeamAnalysisSource(database),
        TechnicalSource(database),
        *build_csv_sources(results_dir),
        RiskAnalysisSource(database, close_price_lookup),
        *build_upstream_sources(results_dir, close_price_lookup),
        OnDemandSource(),
    ]


__all__ = [
    "DailyPicksSource",
    "OnDemandSource",
    "ResearchScreenSource",
    "RiskAnalysisSource",
    "SignalSource",
    "SourceCollectionResult",
    "TeamAnalysisSource",
    "TechnicalSource",
    "UnsupportedSource",
    "build_default_sources",
]