"""TDD: 相同內容的未處理告警不重複寫入（每日排程反覆寫同一則造成的噪音）。"""

from datetime import datetime, timedelta

import pytest

from src.ops import alert_dedup

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 11, 22, 30)


class Alerts:
    def __init__(self, existing=()):
        self.docs = list(existing)

    def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v if not isinstance(v, dict) else doc.get(k) >= v["$gte"] for k, v in query.items()):
                return doc
        return None

    def insert_one(self, doc):
        self.docs.append(doc)


def alert(ts=NOW, resolved=False, message="5 個 collection 未納管"):
    return {"ts": ts, "source": "freshness_audit", "message": message, "resolved": resolved}


def test_a_new_alert_is_written():
    alerts = Alerts()

    assert alert_dedup.insert_once(alerts, alert(), now=NOW) is True
    assert len(alerts.docs) == 1


def test_the_same_unresolved_alert_within_the_window_is_skipped():
    alerts = Alerts([alert(ts=NOW - timedelta(days=1))])

    assert alert_dedup.insert_once(alerts, alert(), now=NOW) is False
    assert len(alerts.docs) == 1


def test_it_is_written_again_as_a_reminder_after_the_window():
    alerts = Alerts([alert(ts=NOW - timedelta(days=8))])

    assert alert_dedup.insert_once(alerts, alert(), now=NOW) is True


def test_a_resolved_alert_does_not_block_a_new_one():
    alerts = Alerts([alert(ts=NOW - timedelta(hours=2), resolved=True)])

    assert alert_dedup.insert_once(alerts, alert(), now=NOW) is True


def test_a_different_message_is_a_different_alert():
    alerts = Alerts([alert(message="10 個 collection 未納管")])

    assert alert_dedup.insert_once(alerts, alert(message="5 個 collection 未納管"), now=NOW) is True
