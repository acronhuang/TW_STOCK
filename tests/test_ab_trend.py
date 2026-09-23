"""verdict A/B 趨勢序列建構測試。"""
from datetime import datetime

import pytest

from src.audit.ab_verdict import build_trend_series


@pytest.mark.unit
def test_build_trend_series_sorts_by_ts_and_skips_invalid():
    docs = [
        {"ts": datetime(2026, 9, 20), "agreement_rate": 0.6},
        {"ts": datetime(2026, 9, 18), "agreement_rate": 0.5},
        {"ts": datetime(2026, 9, 19), "agreement_rate": None},   # None → 跳過
        {"ts": None, "agreement_rate": 0.7},                     # 無 ts → 跳過
        {"agreement_rate": 0.9},                                 # 缺 ts → 跳過
    ]
    series = build_trend_series(docs, "agreement_rate")
    assert series == [
        (datetime(2026, 9, 18), 0.5),
        (datetime(2026, 9, 20), 0.6),
    ]


@pytest.mark.unit
def test_build_trend_series_empty_input_returns_empty():
    assert build_trend_series([], "hit_rate") == []
    assert build_trend_series(None, "hit_rate") == []
