"""TDD: 研究上下文組合器只協調已注入的唯讀依賴。"""

import pytest

from src.research_context.builder import ResearchContextBuilder
from src.research_context.models import (
    FactorSummary,
    RagCitation,
    ResearchContextRequest,
    TeamSummary,
)


pytestmark = pytest.mark.unit


class FakeRepository:
    def __init__(self, teams=None, factors=None):
        self.teams = teams or {}
        self.factors = factors or {}
        self.team_calls = []
        self.factor_calls = []

    def get_team_summary(self, symbol):
        self.team_calls.append(symbol)
        return self.teams.get(symbol)

    def get_factor_summary(self, symbol):
        self.factor_calls.append(symbol)
        return self.factors.get(symbol)


class FakeRetriever:
    def __init__(self, citations=None, error=None):
        self.citations = citations or []
        self.error = error
        self.calls = []

    def search(self, question, max_sources):
        self.calls.append((question, max_sources))
        if self.error is not None:
            raise self.error
        return self.citations


def fixed_now():
    return "2026-10-09T15:30:00+08:00"


def test_builder_preserves_symbol_order_and_warns_when_both_sources_are_missing():
    repository = FakeRepository(
        teams={
            "2330": TeamSummary(
                analysis_date="2026-10-08",
                final_verdict="持有",
                consensus_tally={"持有": 4},
                verify_status="verified",
            )
        }
    )
    retriever = FakeRetriever(
        citations=[
            RagCitation(
                id="rag:docs/a.md:0",
                title="文件",
                path="docs/a.md",
                chunk_idx=0,
                document_date="2026-10-08",
                age_days=1,
                score=0.02,
                excerpt="證據",
            )
        ]
    )

    response = ResearchContextBuilder(repository, retriever, fixed_now).build(
        ResearchContextRequest(question="2330 與 9999 的結論", symbols=["2330", "9999"], max_sources=3)
    )

    assert [item.symbol if item else None for item in response.stocks] == ["2330", None]
    assert response.warnings == ["找不到 9999 的可用資料"]
    assert response.as_of == "2026-10-09T15:30:00+08:00"
    assert response.citations == retriever.citations
    assert repository.team_calls == ["2330", "9999"]
    assert repository.factor_calls == ["2330", "9999"]
    assert retriever.calls == [("2330 與 9999 的結論", 3)]


def test_builder_keeps_stock_when_only_one_research_source_exists():
    repository = FakeRepository(
        teams={
            "2330": TeamSummary(
                analysis_date="2026-10-08",
                final_verdict="持有",
                consensus_tally={"持有": 4},
                verify_status="verified",
            )
        },
        factors={"2317": FactorSummary(date="2026-10-08", pe=15.2)},
    )

    response = ResearchContextBuilder(repository, FakeRetriever(), fixed_now).build(
        ResearchContextRequest(question="比較", symbols=["2330", "2317"])
    )

    assert response.stocks[0].team.final_verdict == "持有"
    assert response.stocks[0].factors is None
    assert response.stocks[1].team is None
    assert response.stocks[1].factors.pe == 15.2
    assert response.warnings == []


def test_builder_propagates_retriever_failure():
    builder = ResearchContextBuilder(FakeRepository(), FakeRetriever(error=RuntimeError("rag unavailable")), fixed_now)

    with pytest.raises(RuntimeError, match="rag unavailable"):
        builder.build(ResearchContextRequest(question="測試問題"))


def test_builder_propagates_repository_failure():
    class FailingRepository(FakeRepository):
        def get_team_summary(self, symbol):
            raise RuntimeError("mongodb unavailable")

    builder = ResearchContextBuilder(FailingRepository(), FakeRetriever(), fixed_now)

    with pytest.raises(RuntimeError, match="mongodb unavailable"):
        builder.build(ResearchContextRequest(question="測試問題", symbols=["2330"]))