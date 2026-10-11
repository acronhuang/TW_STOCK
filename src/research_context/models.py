"""研究上下文的輸入與輸出契約。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Symbol = Annotated[str, Field(pattern=r"^\d{4}$")]


class ResearchContextRequest(StrictModel):
    question: str = Field(min_length=2, max_length=500)
    symbols: list[Symbol] = Field(default_factory=list, max_length=6)
    max_sources: int = Field(default=4, ge=1, le=8)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TeamSummary(StrictModel):
    analysis_date: str | None = None
    final_verdict: str | None = None
    consensus_tally: dict[str, int] | None = None
    verify_status: str | None = None


class FactorSummary(StrictModel):
    date: str | None = None
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    rsi: float | None = None
    dividend_yield: float | None = None


class StockResearchContext(StrictModel):
    symbol: Symbol
    team: TeamSummary | None = None
    factors: FactorSummary | None = None


class RagCitation(StrictModel):
    id: str
    title: str
    path: str
    chunk_idx: int = Field(ge=0)
    document_date: str | None = None
    age_days: int = Field(ge=0)
    score: float
    excerpt: str = Field(max_length=500)


class ResearchContextResponse(StrictModel):
    as_of: str
    question: str
    stocks: list[StockResearchContext | None]
    citations: list[RagCitation]
    warnings: list[str]