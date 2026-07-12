"""Stock 領域實體"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    def change_pct(self) -> Optional[float]:
        if self.open and self.open > 0:
            return (self.close - self.open) / self.open * 100
        return None


@dataclass
class StockFactor:
    """股票因子快照（Value Object）"""
    symbol: str
    date: datetime
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    rsi_14: Optional[float] = None
    operating_margin: Optional[float] = None
    return_1m: Optional[float] = None
    volatility_30d: Optional[float] = None
