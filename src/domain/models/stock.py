"""Stock 領域實體"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Stock:
    """股票基本資訊（Value Object）"""
    symbol: str
    name: str = ''
    industry: str = ''


@dataclass
class StockPrice:
    """日線股價（Entity）"""
    symbol: str
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def change_pct(self) -> float | None:
        if self.open and self.open > 0:
            return (self.close - self.open) / self.open * 100
        return None


@dataclass
class StockFactor:
    """股票因子快照（Value Object）"""
    symbol: str
    date: datetime
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    rsi_14: float | None = None
    operating_margin: float | None = None
    return_1m: float | None = None
    volatility_30d: float | None = None
