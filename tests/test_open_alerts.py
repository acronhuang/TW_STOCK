"""未解決告警彙整測試。"""
from datetime import datetime

import pytest

from src.monitoring.data_quality import summarize_open_alerts


@pytest.mark.unit
def test_summarize_groups_by_source_and_counts():
    docs = [
        {"ts": datetime(2026, 9, 20), "source": "verdict_ab_eval", "message": "一致率低"},
        {"ts": datetime(2026, 9, 21), "source": "verdict_attribution", "message": "命中率跌"},
        {"ts": datetime(2026, 9, 22), "source": "verdict_ab_eval", "message": "一致率低2"},
    ]
    s = summarize_open_alerts(docs)
    assert s["total"] == 3
    assert s["by_source"] == {"verdict_ab_eval": 2, "verdict_attribution": 1}
    # latest 依 ts 由新到舊
    assert s["latest"][0]["message"] == "一致率低2"


@pytest.mark.unit
def test_summarize_empty():
    s = summarize_open_alerts([])
    assert s["total"] == 0
    assert s["by_source"] == {}
    assert s["latest"] == []
