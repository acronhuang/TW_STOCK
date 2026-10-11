"""研究上下文的 MongoDB 讀取邊界。"""

from typing import Any, Protocol

from bson import Decimal128

from src.domain.collections import COLL_STOCK_FACTORS, COLL_TEAM_ANALYSIS
from src.research_context.models import FactorSummary, TeamSummary


class ResearchRepository(Protocol):
    def get_team_summary(self, symbol: str) -> TeamSummary | None: ...

    def get_factor_summary(self, symbol: str) -> FactorSummary | None: ...


class MongoResearchRepository:
    def __init__(self, database: Any) -> None:
        self._database = database

    def get_team_summary(self, symbol: str) -> TeamSummary | None:
        document = self._database[COLL_TEAM_ANALYSIS].find_one(
            {"symbol": symbol},
            {
                "_id": 0,
                "date": 1,
                "final_verdict": 1,
                "consensus.tally": 1,
                "verify.status": 1,
            },
            sort=[("date", -1)],
        )
        if document is None:
            return None
        consensus = document.get("consensus") or {}
        verify = document.get("verify") or {}
        return TeamSummary(
            analysis_date=_date_text(document.get("date")),
            final_verdict=document.get("final_verdict"),
            consensus_tally=consensus.get("tally"),
            verify_status=verify.get("status"),
        )

    def get_factor_summary(self, symbol: str) -> FactorSummary | None:
        document = self._database[COLL_STOCK_FACTORS].find_one(
            {"symbol": symbol},
            {
                "_id": 0,
                "date": 1,
                "pe": 1,
                "pb": 1,
                "roe": 1,
                "rsi": 1,
                "dividend_yield": 1,
            },
            sort=[("date", -1)],
        )
        if document is None:
            return None
        return FactorSummary(
            date=_date_text(document.get("date")),
            pe=_float_or_none(document.get("pe")),
            pb=_float_or_none(document.get("pb")),
            roe=_float_or_none(document.get("roe")),
            rsi=_float_or_none(document.get("rsi")),
            dividend_yield=_float_or_none(document.get("dividend_yield")),
        )


def _date_text(value: object) -> str | None:
    return str(value)[:10] if value is not None else None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    return float(value)