"""Portfolio 領域實體"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """持倉（Entity）"""
    symbol: str
    shares: int
    avg_cost: float
    first_buy_date: Optional[datetime] = None

    @property
    def total_cost(self) -> float:
        return self.shares * self.avg_cost

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_cost) * self.shares

    def unrealized_pnl_pct(self, current_price: float) -> float:
        if self.avg_cost <= 0:
            return 0
        return (current_price - self.avg_cost) / self.avg_cost * 100


@dataclass
class Trade:
    """交易紀錄（Value Object）"""
    symbol: str
    action: str    # BUY / SELL
    shares: int
    price: float
    date: datetime
    commission: float = 0
    note: str = ''
