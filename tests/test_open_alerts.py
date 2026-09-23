"""未解決告警彙整測試。"""
from datetime import datetime

import pytest

from src.monitoring.data_quality import auto_resolve_alerts, summarize_open_alerts


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


class _UpdColl:
    def __init__(self):
        self.calls = []

    def update_many(self, flt, upd):
        self.calls.append((flt, upd))
        return type("R", (), {"modified_count": 2})()


class _UpdDB:
    def __init__(self):
        self.coll = _UpdColl()

    def __getitem__(self, name):
        return self.coll


@pytest.mark.unit
def test_auto_resolve_marks_matching_source():
    db = _UpdDB()
    now = datetime(2026, 9, 23)
    n = auto_resolve_alerts(db, "verdict_ab_eval", now=now)
    assert n == 2
    flt, upd = db.coll.calls[0]
    assert flt == {"source": "verdict_ab_eval", "resolved": {"$ne": True}}
    assert upd["$set"]["resolved"] is True
    assert upd["$set"]["resolved_at"] == now
    assert upd["$set"]["resolved_reason"].startswith("auto:")
