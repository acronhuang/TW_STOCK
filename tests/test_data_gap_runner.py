"""TDD: 缺口登記簿對帳與修復流程（偵測 → 判斷可否回補 → 補 → 驗證 → 登記未補項）。"""

from datetime import datetime

import pytest

from src.data_gap import runner
from src.data_gap.models import Gap

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 12, 6, 10)


class Register:
    def __init__(self, docs=None):
        self.docs = {d["_id"]: d for d in (docs or [])}
        self.saved = []

    def load(self):
        return dict(self.docs)

    def save(self, docs):
        self.saved.extend(docs)
        for doc in docs:
            self.docs[doc["_id"]] = doc


class Alerts:
    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)


def make(detections, executed=None, **options):
    """detections: 依序回傳的缺口清單（第一次=補前，之後=補後驗證）。"""
    calls = iter(detections)
    state = {"last": detections[-1]}

    def detect():
        try:
            state["last"] = next(calls)
        except StopIteration:
            pass
        return state["last"]

    commands = executed if executed is not None else []
    register, alerts = Register(options.pop("existing", None)), Alerts()
    summary_kwargs = dict(detect=detect, execute=lambda c: commands.append(c) or 0, register=register,
                          alert=alerts, now=NOW)
    summary_kwargs.update(options)
    return register, alerts, commands, summary_kwargs


def gap(collection, day="20260915", kind="gap"):
    return Gap(collection, day, kind)


def test_a_recoverable_gap_is_repaired_verified_and_registered_as_repaired():
    register, alerts, commands, kwargs = make([([gap("stock_price")], frozenset()), ([], frozenset())])

    summary = runner.run(apply=True, **kwargs)

    assert ("backfill_by_date.py", "--date", "20260915", "--apply") in commands
    assert register.docs["stock_price:20260915:gap"]["status"] == "repaired"
    assert summary["repaired"] == 1 and alerts.messages == []


def test_a_repair_that_does_not_close_the_gap_stays_open_and_counts_an_attempt():
    register, _, _, kwargs = make([([gap("stock_price")], frozenset()), ([gap("stock_price")], frozenset())])

    runner.run(apply=True, **kwargs)

    doc = register.docs["stock_price:20260915:gap"]
    assert doc["status"] == "open" and doc["attempts"] == 1


def test_after_the_attempt_budget_the_gap_is_failed_alerted_once_and_no_longer_retried():
    existing = [{"_id": "stock_price:20260915:gap", "collection": "stock_price", "day": "20260915", "kind": "gap",
                 "status": "open", "attempts": 2, "first_seen": NOW, "alerted": False}]
    register, alerts, commands, kwargs = make(
        [([gap("stock_price")], frozenset()), ([gap("stock_price")], frozenset())], existing=existing)

    runner.run(apply=True, max_attempts=3, **kwargs)

    assert register.docs["stock_price:20260915:gap"]["status"] == "failed"
    assert len(alerts.messages) == 1
    commands.clear()
    runner.run(apply=True, max_attempts=3, **kwargs)
    assert commands == [] and len(alerts.messages) == 1


def test_unrecoverable_gaps_are_registered_and_alerted_but_never_executed():
    register, alerts, commands, kwargs = make([([gap("securities_lending", "20260916")], frozenset())])

    runner.run(apply=True, **kwargs)

    doc = register.docs["securities_lending:20260916:gap"]
    assert doc["status"] == "unrecoverable" and "最新" in doc["reason"]
    assert commands == [] and len(alerts.messages) == 1


def test_derived_tables_are_registered_for_a_human_not_backfilled():
    register, alerts, commands, kwargs = make([([gap("stock_factors", "20260916")], frozenset())])

    runner.run(apply=True, **kwargs)

    assert register.docs["stock_factors:20260916:gap"]["status"] == "derived"
    assert commands == [] and len(alerts.messages) == 1


def test_a_suspected_market_closure_is_registered_without_any_repair():
    register, _, commands, kwargs = make([([gap("stock_price", "20260710")], frozenset({"20260710"}))])

    runner.run(apply=True, **kwargs)

    assert register.docs["stock_price:20260710:gap"]["status"] == "closure_suspected"
    assert commands == []


def test_a_gap_that_disappears_on_its_own_is_marked_resolved_not_repaired():
    existing = [{"_id": "securities_lending:20260916:gap", "collection": "securities_lending", "day": "20260916",
                 "kind": "gap", "status": "unrecoverable", "attempts": 0, "first_seen": NOW, "alerted": True}]
    register, _, _, kwargs = make([([], frozenset())], existing=existing)

    runner.run(apply=True, **kwargs)

    doc = register.docs["securities_lending:20260916:gap"]
    assert doc["status"] == "resolved" and doc["resolved_at"] == NOW


def test_the_per_run_budget_limits_how_many_days_are_repaired_and_the_price_calendar_goes_first():
    gaps = [gap("institutional_flow", "20260916"), gap("stock_price", "20260915"), gap("institutional_flow", "20260917")]
    _, _, commands, kwargs = make([(gaps, frozenset()), (gaps, frozenset())])

    runner.run(apply=True, max_items=2, **kwargs)

    assert commands[0][0] == "backfill_by_date.py"
    assert len({c[2] if c[0] == "backfill_by_date.py" else c[2] for c in commands}) <= 2


def test_dry_run_plans_but_executes_and_writes_nothing():
    register, alerts, commands, kwargs = make([([gap("stock_price"), gap("securities_lending")], frozenset())])

    summary = runner.run(apply=False, **kwargs)

    assert commands == [] and register.saved == [] and alerts.messages == []
    assert summary["planned"] == 1 and summary["applied"] is False


def test_a_failing_command_does_not_abort_the_run():
    def boom(command):
        raise RuntimeError("upstream blocked")

    register, _, _, kwargs = make([([gap("stock_price")], frozenset()), ([gap("stock_price")], frozenset())])
    kwargs["execute"] = boom

    runner.run(apply=True, **kwargs)

    assert register.docs["stock_price:20260915:gap"]["attempts"] == 1


def _alerted_manual(first_alert_days_ago, last_reminded_days_ago=None):
    from datetime import timedelta
    doc = {"_id": "securities_lending:20260916:gap", "collection": "securities_lending", "day": "20260916",
           "kind": "gap", "status": "unrecoverable", "attempts": 0, "first_seen": NOW - timedelta(days=30),
           "alerted": True, "alerted_at": NOW - timedelta(days=first_alert_days_ago)}
    if last_reminded_days_ago is not None:
        doc["last_reminded"] = NOW - timedelta(days=last_reminded_days_ago)
    return doc


def test_an_unresolved_manual_item_is_reminded_after_a_week_not_before():
    gaps = [([gap("securities_lending", "20260916")], frozenset())]
    register, alerts, _, kwargs = make(gaps, existing=[_alerted_manual(3)])
    runner.run(apply=True, **kwargs)
    assert alerts.messages == []

    register, alerts, _, kwargs = make(gaps, existing=[_alerted_manual(8)])
    runner.run(apply=True, **kwargs)
    assert len(alerts.messages) == 1 and "仍未處理" in alerts.messages[0]
    assert register.docs["securities_lending:20260916:gap"]["last_reminded"] == NOW


def test_a_reminder_is_not_repeated_until_another_week_has_passed():
    gaps = [([gap("securities_lending", "20260916")], frozenset())]
    _, alerts, _, kwargs = make(gaps, existing=[_alerted_manual(20, last_reminded_days_ago=2)])

    runner.run(apply=True, **kwargs)

    assert alerts.messages == []


def test_the_first_alert_records_when_it_was_sent():
    register, _, _, kwargs = make([([gap("securities_lending", "20260916")], frozenset())])

    runner.run(apply=True, **kwargs)

    assert register.docs["securities_lending:20260916:gap"]["alerted_at"] == NOW
