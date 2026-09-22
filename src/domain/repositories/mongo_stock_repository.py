"""MongoDB 實作 StockRepository（Infrastructure Layer）

此檔案放在 domain/repositories/ 是為了方便引用，
嚴格 DDD 應放在 infrastructure/ 但為實用性保留在此。
"""
from __future__ import annotations

from datetime import datetime

from bson import Decimal128

from ..collections import COLL_QUARTERLY_EARNINGS, COLL_STOCK_FACTORS, COLL_STOCK_PRICE
from ..models.stock import StockFactor, StockPrice
from .stock_repository import StockRepository


def _tof(v) -> float | None:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class MongoStockRepository(StockRepository):
    """MongoDB 實作"""

    def __init__(self,
                 mongo_uri: str | None = None,
                 db_name: str | None = None):
        # 預設走 src.config 單一真相源（env 可覆寫）；顯式 mongo_uri 優先（相容舊呼叫）。
        if mongo_uri is None:
            from src.config import get_db
            self.db = get_db(db_name)
        else:
            from pymongo import MongoClient
            self.db = MongoClient(mongo_uri)[db_name or "tw_stock_analysis"]

    def get_price(self, symbol: str, days: int = 20) -> list[StockPrice]:
        records = list(self.db[COLL_STOCK_PRICE].find(
            {'symbol': symbol},
            {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
        ).sort('date', -1).limit(days))

        return [StockPrice(
            symbol=symbol,
            date=r['date'],
            open=_tof(r.get('open')) or 0,
            high=_tof(r.get('high')) or 0,
            low=_tof(r.get('low')) or 0,
            close=_tof(r.get('close')) or 0,
            volume=_tof(r.get('volume')) or 0,
        ) for r in reversed(records)]

    def get_latest_price(self, symbol: str) -> float | None:
        doc = self.db[COLL_STOCK_PRICE].find_one(
            {'symbol': symbol}, {'close': 1}, sort=[('date', -1)])
        return _tof(doc['close']) if doc else None

    def get_factor(self, symbol: str) -> StockFactor | None:
        doc = self.db[COLL_STOCK_FACTORS].find_one(
            {'symbol': symbol}, sort=[('date', -1)])
        if not doc:
            return None
        return StockFactor(
            symbol=symbol,
            date=doc.get('date', datetime.now()),
            pe_ratio=_tof(doc.get('pe_ratio')),
            pb_ratio=_tof(doc.get('pb_ratio')),
            dividend_yield=_tof(doc.get('dividend_yield')),
            roe=_tof(doc.get('roe')),
            rsi_14=_tof(doc.get('rsi_14')),
            operating_margin=_tof(doc.get('operating_margin')),
            return_1m=_tof(doc.get('return_1m')),
            volatility_30d=_tof(doc.get('volatility_30d')),
        )

    def get_all_symbols(self) -> list[str]:
        return sorted(self.db[COLL_STOCK_FACTORS].distinct('symbol'))

    def get_quarterly_earnings(self, symbol: str, limit: int = 4) -> list[dict]:
        return list(self.db[COLL_QUARTERLY_EARNINGS].find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(limit))
