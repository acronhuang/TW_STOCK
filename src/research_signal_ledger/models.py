"""研究訊號成效帳本的嚴格資料契約。"""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, field_validator

from src.research_context.models import StrictModel, Symbol


class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    RISK_REDUCE = "risk_reduce"
    HOLD = "hold"
    OBSERVE = "observe"


class ResearchSignalSnapshot(StrictModel):
    snapshot_key: str = Field(min_length=32, max_length=64)
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    source_event_id: str = Field(min_length=1, max_length=200)
    symbol: Symbol
    analysis_date: date
    available_at: datetime
    captured_at: datetime
    signal_kind: str = Field(min_length=1, max_length=80)
    direction: SignalDirection
    evaluation_enabled: bool
    score: float | None = Field(default=None, ge=0, le=100)
    rule_version: str = Field(min_length=1, max_length=80)
    price_at_signal: float = Field(gt=0)
    source_payload: dict[str, JsonValue]
    benchmark_profile: str = Field(min_length=1, max_length=80)
    cost_profile: str = "tw_cash_default_v1"

    @field_validator("source_event_id")
    @classmethod
    def source_event_requires_historical_identifier(cls, value: str) -> str:
        if value.strip().lower() == "latest":
            raise ValueError("source_event_id must identify a historical source event")
        return value

    @field_validator("available_at", "captured_at")
    @classmethod
    def timestamps_require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class ResearchBenchmarkSnapshot(StrictModel):
    benchmark_key: str = Field(min_length=1, max_length=200)
    profile: Literal["market_equal_weight_liquid_tw_v1", "analysis_pool_v1"]
    analysis_date: date
    symbol_count: int = Field(ge=1)
    symbols: list[Symbol] = Field(min_length=1)
    membership_hash: str = Field(min_length=1, max_length=64)
    captured_at: datetime

    @field_validator("captured_at")
    @classmethod
    def captured_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class ResearchSignalOutcome(StrictModel):
    outcome_key: str = Field(min_length=1, max_length=200)
    snapshot_key: str = Field(min_length=32, max_length=64)
    horizon_trading_days: Literal[5, 10, 20]
    revision: int = Field(ge=1)
    entry_date: date
    exit_date: date
    entry_adj_close: float = Field(gt=0)
    exit_adj_close: float = Field(gt=0)
    direction: SignalDirection
    gross_return_pct: float
    net_return_pct: float
    excess_mkt_pct: float | None
    excess_pool_pct: float | None
    hit: bool | None
    cost_pct: float = Field(ge=0)
    price_data_as_of: datetime
    evaluated_at: datetime
    supersedes_outcome_key: str | None = None

    @field_validator("price_data_as_of", "evaluated_at")
    @classmethod
    def outcome_timestamps_require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class CaptureRun(StrictModel):
    run_id: str = Field(min_length=1, max_length=200)
    as_of: date
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    captured: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    no_output: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    failed: int = Field(ge=0)
    error_summary: str | None = Field(default=None, max_length=1000)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class MethodStatus(StrictModel):
    source: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    signal_kind: str = Field(min_length=1, max_length=80)
    policy_version: str = Field(min_length=1, max_length=80)
    state: Literal["observe", "active", "degraded", "disabled"]
    effective_weight: float = Field(ge=0, le=1)
    evaluated_horizon: Literal[20]
    sample_size: int = Field(ge=0)
    independent_analysis_days: int = Field(ge=0)
    failure_streak: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    decided_at: datetime
    evidence_outcome_keys: list[str]

    @field_validator("decided_at")
    @classmethod
    def decided_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value