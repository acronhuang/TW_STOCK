"""研究訊號成效帳本的固定 benchmark 成員名單。"""

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Iterable, Mapping, Sequence

from src.research_signal_ledger.evaluator import TradingPrice
from src.research_signal_ledger.models import ResearchBenchmarkSnapshot
from src.strategy.screen_liquidity import MIN_VOL_LOTS

LIQUIDITY_WINDOW_DAYS = 20
_STOCK_SYMBOL = re.compile(r"^[1-9]\d{3}$")  # 0 開頭的四碼為 ETF，不屬個股基準。


def select_liquid_symbols(volume_by_symbol: Mapping[str, Sequence[float]]) -> list[str]:
    """四碼個股代號且近 20 日均量(股)達共用門檻者；窗口不足視為不具流動性證據。"""
    selected = []
    for symbol, volumes in volume_by_symbol.items():
        if not _STOCK_SYMBOL.match(symbol) or len(volumes) < LIQUIDITY_WINDOW_DAYS:
            continue
        window = volumes[:LIQUIDITY_WINDOW_DAYS]
        if sum(window) / len(window) / 1000 >= MIN_VOL_LOTS:
            selected.append(symbol)
    return sorted(selected)

from src.research_signal_ledger.evaluator import TradingPrice
from src.research_signal_ledger.models import ResearchBenchmarkSnapshot


def build_market_benchmark(
    as_of: date, rows: Iterable[TradingPrice]
) -> ResearchBenchmarkSnapshot:
    """以已有正向還原價的標的建立當日等權市場 benchmark。"""
    symbols = sorted({row.symbol for row in rows if row.date <= as_of and row.adj_close > 0})
    membership = json.dumps(symbols, separators=(",", ":"))
    membership_hash = hashlib.sha256(membership.encode("utf-8")).hexdigest()
    return ResearchBenchmarkSnapshot(
        benchmark_key=f"market_equal_weight_liquid_tw_v1:{as_of.isoformat()}:{membership_hash}",
        profile="market_equal_weight_liquid_tw_v1",
        analysis_date=as_of,
        symbol_count=len(symbols),
        symbols=symbols,
        membership_hash=membership_hash,
        captured_at=datetime.now(UTC),
    )