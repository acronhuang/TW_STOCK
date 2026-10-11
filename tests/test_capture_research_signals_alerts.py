"""TDD: capture 來源失敗必須告警（去重、成功後自動消解）；這是帳本豁免新鮮度審核的前提。"""

from datetime import datetime, timedelta

import pytest

from scripts import capture_research_signals as module
from src.research_signal_ledger.sources.base import SourceCollectionResult


pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 12, 22, 55)


class Alerts:
    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.inserted = []
        self.resolved_queries = []

    def find_one(self, query):
        for document in self.documents:
            if document.get("source") != query.get("source"):
                continue
            if query.get("resolved") == {"$ne": True} and document.get("resolved") is True:
                continue
            since = query.get("ts", {}).get("$gte")
            if since and document["ts"] < since:
                continue
            return document
        return None

    def insert_one(self, document):
        self.inserted.append(document)
        self.documents.append(document)

    def update_many(self, query, update):
        self.resolved_queries.append((query, update))
        for document in self.documents:
            if document.get("source") == query["source"] and document.get("resolved") is not True:
                document.update(update["$set"])


def failure(name, message="boom"):
    return SourceCollectionResult(name, [], "failed", message)


def test_failed_sources_raise_one_alert_listing_all_of_them():
    alerts = Alerts()

    module.alert_failed_sources(alerts, [failure("chip"), failure("risk", "db down")], NOW)

    assert len(alerts.inserted) == 1
    alert = alerts.inserted[0]
    assert alert["source"] == "research_signal_ledger"
    assert alert["resolved"] is False
    assert "chip" in alert["message"] and "risk" in alert["message"] and "db down" in alert["message"]


def test_a_repeat_failure_within_a_day_does_not_raise_a_second_alert():
    alerts = Alerts([{"source": "research_signal_ledger", "resolved": False, "ts": NOW - timedelta(hours=3)}])

    module.alert_failed_sources(alerts, [failure("chip")], NOW)

    assert alerts.inserted == []


def test_an_old_unresolved_alert_does_not_suppress_a_new_one():
    alerts = Alerts([{"source": "research_signal_ledger", "resolved": False, "ts": NOW - timedelta(hours=30)}])

    module.alert_failed_sources(alerts, [failure("chip")], NOW)

    assert len(alerts.inserted) == 1


def test_no_failures_resolve_any_open_alert_and_raise_nothing():
    alerts = Alerts([{"source": "research_signal_ledger", "resolved": False, "ts": NOW - timedelta(hours=3)}])

    module.alert_failed_sources(alerts, [], NOW)

    assert alerts.inserted == []
    assert alerts.documents[0]["resolved"] is True
    assert "auto" in alerts.documents[0]["resolved_reason"]


def test_unsupported_and_no_output_are_not_failures():
    assert module.failed_results(
        [
            SourceCollectionResult("a", [], "no_output"),
            SourceCollectionResult("b", [], "unsupported"),
            SourceCollectionResult("c", [], "captured"),
            SourceCollectionResult("d", [], "failed", "x"),
        ]
    ) == [SourceCollectionResult("d", [], "failed", "x")]


class RecordingDatabase:
    def __init__(self):
        self.alerts = Alerts()

    def __getitem__(self, name):
        if name == "schedule_alerts":
            return self.alerts
        return NoPrices()


class NoPrices:
    def find(self, query, projection=None):
        return []


class Repo:
    def __init__(self, _):
        pass

    def insert_snapshots(self, snapshots):
        raise AssertionError("no snapshots expected")

    def record_capture_run(self, run):
        pass


class BoomSource:
    name = "boom"

    def collect(self, as_of):
        raise RuntimeError("source unavailable")


def test_the_cli_raises_an_alert_when_a_source_fails(monkeypatch):
    database = RecordingDatabase()
    monkeypatch.setattr(module, "get_db", lambda: database)
    monkeypatch.setattr(module, "ResearchSignalLedgerRepository", Repo)
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [BoomSource()])

    assert module.main(["--as-of", "2026-10-12"]) == 1

    assert len(database.alerts.inserted) == 1


def test_dry_run_never_touches_alerts(monkeypatch):
    database = RecordingDatabase()
    monkeypatch.setattr(module, "get_db", lambda: database)
    monkeypatch.setattr(module, "build_default_sources", lambda *_: [BoomSource()])

    module.main(["--as-of", "2026-10-12", "--dry-run"])

    assert database.alerts.inserted == []
    assert database.alerts.resolved_queries == []


@pytest.mark.integration
def test_real_mongo_dedupes_within_a_day_and_resolves_after_recovery(write_db):
    alerts = write_db["schedule_alerts"]
    alerts.delete_many({"source": module.ALERT_SOURCE})
    now = datetime.now()

    module.alert_failed_sources(alerts, [failure("chip")], now)
    module.alert_failed_sources(alerts, [failure("chip"), failure("risk")], now + timedelta(hours=2))
    assert alerts.count_documents({"source": module.ALERT_SOURCE, "resolved": False}) == 1

    module.alert_failed_sources(alerts, [], now + timedelta(hours=3))
    assert alerts.count_documents({"source": module.ALERT_SOURCE, "resolved": False}) == 0
    assert alerts.count_documents({"source": module.ALERT_SOURCE, "resolved": True}) == 1

    module.alert_failed_sources(alerts, [failure("chip")], now + timedelta(hours=4))
    assert alerts.count_documents({"source": module.ALERT_SOURCE, "resolved": False}) == 1
    alerts.delete_many({"source": module.ALERT_SOURCE})
