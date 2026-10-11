"""TDD: 研究訊號成效帳本的嚴格資料契約。"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection


pytestmark = pytest.mark.unit


def snapshot(**overrides):
    data = {
        "snapshot_key": "a" * 64,
        "source": "daily_picks",
        "source_event_id": "sha256:abc:2026-10-10",
        "symbol": "2330",
        "analysis_date": date(2026, 10, 10),
        "available_at": datetime(2026, 10, 10, 20, tzinfo=timezone.utc),
        "captured_at": datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
        "signal_kind": "factor_rank",
        "direction": SignalDirection.LONG,
        "evaluation_enabled": True,
        "price_at_signal": 100.0,
        "source_payload": {"rank": 1},
        "benchmark_profile": "market_equal_weight_liquid_tw_v1",
        "rule_version": "daily_picks_v1",
    }
    return ResearchSignalSnapshot(**(data | overrides))


def test_snapshot_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        snapshot(unexpected="no")


def test_snapshot_rejects_non_taiwan_symbol():
    with pytest.raises(ValidationError):
        snapshot(symbol="AAPL")