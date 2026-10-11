"""組合唯讀研究上下文，不依賴任何平台 adapter。"""

from collections.abc import Callable

from src.research_context.models import (
    ResearchContextRequest,
    ResearchContextResponse,
    StockResearchContext,
)
from src.research_context.repository import ResearchRepository
from src.research_context.retriever import RagRetriever


class ResearchContextBuilder:
    def __init__(
        self,
        repository: ResearchRepository,
        retriever: RagRetriever,
        now: Callable[[], str],
    ) -> None:
        self._repository = repository
        self._retriever = retriever
        self._now = now

    def build(self, request: ResearchContextRequest) -> ResearchContextResponse:
        citations = self._retriever.search(request.question, request.max_sources)
        stocks: list[StockResearchContext | None] = []
        warnings: list[str] = []

        for symbol in request.symbols:
            team = self._repository.get_team_summary(symbol)
            factors = self._repository.get_factor_summary(symbol)
            if team is None and factors is None:
                stocks.append(None)
                warnings.append(f"找不到 {symbol} 的可用資料")
                continue
            stocks.append(StockResearchContext(symbol=symbol, team=team, factors=factors))

        return ResearchContextResponse(
            as_of=self._now(),
            question=request.question,
            stocks=stocks,
            citations=citations,
            warnings=warnings,
        )