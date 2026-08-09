"""Stock Repository 介面（DDD — 抽象層）

具體實作在 infrastructure 層（如 MongoStockRepository）。
Domain 層只依賴這個介面，不知道底層是 MongoDB 還是其他。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.stock import StockFactor, StockPrice


class StockRepository(ABC):
    """股票資料存取介面"""

    @abstractmethod
    def get_price(self, symbol: str, days: int = 20) -> list[StockPrice]:
        """取得近 N 日股價"""
        ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float | None:
        """取得最新收盤價"""
        ...

    @abstractmethod
    def get_factor(self, symbol: str) -> StockFactor | None:
        """取得最新因子"""
        ...

    @abstractmethod
    def get_all_symbols(self) -> list[str]:
        """取得所有有資料的股票代號"""
        ...

    @abstractmethod
    def get_quarterly_earnings(self, symbol: str, limit: int = 4) -> list[dict]:
        """取得近 N 季季報"""
        ...
