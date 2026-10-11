"""TDD: 平台中立研究上下文的請求與回應契約。"""

import pytest
from pydantic import ValidationError

from src.research_context.models import (
    FactorSummary,
    RagCitation,
    ResearchContextRequest,
    ResearchContextResponse,
    StockResearchContext,
    TeamSummary,
)


pytestmark = pytest.mark.unit


def test_request_strips_question_before_length_validation():
    request = ResearchContextRequest(question="  2330 的風險  ")

    assert request.question == "2330 的風險"
    assert request.symbols == []
    assert request.max_sources == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "  "},
        {"question": "ok", "symbols": ["TSMC"]},
        {"question": "ok", "symbols": ["2330"] * 7},
        {"question": "ok", "max_sources": 0},
        {"question": "ok", "max_sources": 9},
        {"question": "ok", "unexpected": True},
    ],
)
def test_request_rejects_each_invalid_contract_case(payload):
    with pytest.raises(ValidationError):
        ResearchContextRequest(**payload)


def test_response_serializes_only_allowlisted_research_fields():
    response = ResearchContextResponse(
        as_of="2026-10-09T15:30:00+08:00",
        question="2330 的風險",
        stocks=[
            StockResearchContext(
                symbol="2330",
                team=TeamSummary(
                    analysis_date="2026-10-08",
                    final_verdict="持有",
                    consensus_tally={"持有": 4},
                    verify_status="verified",
                ),
                factors=FactorSummary(date="2026-10-08", pe=20.1, roe=28.0),
            )
        ],
        citations=[
            RagCitation(
                id="rag:docs/example.md:0",
                title="文件標題",
                path="docs/example.md",
                chunk_idx=0,
                document_date="2026-10-09",
                age_days=0,
                score=0.021,
                excerpt="可追溯的原文節錄",
            )
        ],
        warnings=[],
    )

    assert response.model_dump() == {
        "as_of": "2026-10-09T15:30:00+08:00",
        "question": "2330 的風險",
        "stocks": [
            {
                "symbol": "2330",
                "team": {
                    "analysis_date": "2026-10-08",
                    "final_verdict": "持有",
                    "consensus_tally": {"持有": 4},
                    "verify_status": "verified",
                },
                "factors": {
                    "date": "2026-10-08",
                    "pe": 20.1,
                    "pb": None,
                    "roe": 28.0,
                    "rsi": None,
                    "dividend_yield": None,
                },
            }
        ],
        "citations": [
            {
                "id": "rag:docs/example.md:0",
                "title": "文件標題",
                "path": "docs/example.md",
                "chunk_idx": 0,
                "document_date": "2026-10-09",
                "age_days": 0,
                "score": 0.021,
                "excerpt": "可追溯的原文節錄",
            }
        ],
        "warnings": [],
    }


def test_summary_models_reject_unallowlisted_fields():
    with pytest.raises(ValidationError):
        TeamSummary(
            analysis_date="2026-10-08",
            final_verdict="持有",
            consensus_tally={"持有": 4},
            verify_status="verified",
            role_reports={"prompt": "must not escape"},
        )