"""TDD: 節點掛掉時等待重試；失敗項補跑；批次完成度告警。"""

from datetime import date, datetime, timedelta

import pytest

from src.moe import completion, preflight, retry

pytestmark = pytest.mark.unit

N28 = "http://172.16.9.28:11434"
REQUIRED = {N28: {"gemma2:9b"}}


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"models": [{"name": "gemma2:9b"}]}


def flaky_get(failures):
    state = {"calls": 0}

    def get(url, timeout):
        state["calls"] += 1
        if state["calls"] <= failures:
            raise ConnectionError("down")
        return Response()

    get.state = state
    return get


# ── 等待重試 ──────────────────────────────────────────────────────────

def test_waits_until_the_node_comes_back():
    sleeps = []
    get = flaky_get(2)

    preflight.wait_until_ready(REQUIRED, retries=5, interval_sec=1800, sleep=sleeps.append, get=get)

    assert sleeps == [1800, 1800]
    assert get.state["calls"] == 3


def test_gives_up_after_the_retry_budget_with_the_last_problems():
    sleeps = []

    with pytest.raises(preflight.OllamaNotReady) as error:
        preflight.wait_until_ready(REQUIRED, retries=2, interval_sec=60, sleep=sleeps.append, get=flaky_get(99))

    assert sleeps == [60, 60]
    assert N28 in str(error.value)


def test_zero_retries_checks_once_and_never_sleeps():
    sleeps = []

    with pytest.raises(preflight.OllamaNotReady):
        preflight.wait_until_ready(REQUIRED, retries=0, interval_sec=60, sleep=sleeps.append, get=flaky_get(99))

    assert sleeps == []


def test_waiting_is_announced_so_a_long_wait_is_not_silent():
    messages = []

    preflight.wait_until_ready(REQUIRED, retries=3, interval_sec=10, sleep=lambda s: None,
                               get=flaky_get(1), on_wait=messages.append)

    assert len(messages) == 1 and N28 in messages[0]


# ── 補跑目標 ──────────────────────────────────────────────────────────

FAILED = "分析失敗: HTTPConnectionPool"


def test_a_failed_role_report_needs_retry():
    assert retry.needs_retry({"reports": {"a": "ok", "b": FAILED}, "advisor": "評級：買進"}) is True


def test_a_skipped_advisor_needs_retry():
    assert retry.needs_retry({"reports": {"a": "ok"}, "advisor": "整合略過：角色報告全數為錯誤訊息"}) is True


def test_a_clean_or_still_pending_document_does_not_need_retry():
    assert retry.needs_retry({"reports": {"a": "ok"}, "advisor": "評級：買進"}) is False
    assert retry.needs_retry({"reports": {"a": "ok"}, "advisor": None}) is False


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.query = None

    def find(self, query, projection=None):
        self.query = query
        return self.documents


def doc(symbol, day, reports=None, advisor="評級：買進"):
    return {"symbol": symbol, "name": symbol, "date": datetime(2026, 10, day), "reports": reports or {"a": "ok"},
            "advisor": advisor}


def test_targets_are_grouped_by_date_and_only_include_failures():
    collection = Collection([doc("2330", 9, {"a": FAILED}), doc("2317", 9), doc("2454", 10, {"a": FAILED})])

    targets = retry.find_retry_targets(collection, date(2026, 10, 10), days=2)

    assert {day: [t["symbol"] for t in items] for day, items in targets.items()} == {
        date(2026, 10, 9): ["2330"],
        date(2026, 10, 10): ["2454"],
    }


def test_the_default_window_is_recent_days_only():
    collection = Collection([])

    retry.find_retry_targets(collection, date(2026, 10, 10), days=2)

    assert collection.query["date"] == {"$gte": datetime(2026, 10, 8), "$lt": datetime(2026, 10, 11)}


def test_an_explicit_date_overrides_the_window():
    collection = Collection([])

    retry.find_retry_targets(collection, date(2026, 10, 14), days=2, only_date=date(2026, 10, 9))

    assert collection.query["date"] == {"$gte": datetime(2026, 10, 9), "$lt": datetime(2026, 10, 10)}


# ── 完成度 ────────────────────────────────────────────────────────────

def complete_doc(votes=3):
    return {"models": {"a": "m"}, "final_verdict": "買進", "consensus": {"n": votes}}


def test_a_document_needs_models_a_verdict_and_at_least_two_valid_votes():
    assert completion.is_complete(complete_doc(3)) is True
    assert completion.is_complete(complete_doc(2)) is True
    assert completion.is_complete(complete_doc(1)) is False
    assert completion.is_complete({"models": {}, "final_verdict": "買進", "consensus": {"n": 3}}) is False
    assert completion.is_complete({"models": {"a": "m"}, "final_verdict": None, "consensus": {"n": 3}}) is False


def test_stats_report_the_ratio():
    stats = completion.completion_stats([complete_doc(), complete_doc(), complete_doc(0), complete_doc()])

    assert stats == {"total": 4, "complete": 3, "ratio": 0.75}


class Alerts:
    def __init__(self):
        self.inserted = []
        self.updated = []
        self.open = None

    def find_one(self, query):
        return self.open

    def insert_one(self, document):
        self.inserted.append(document)

    def update_many(self, query, update):
        self.updated.append((query, update))


NOW = datetime(2026, 10, 14, 7, 0)


def test_a_low_ratio_raises_one_alert():
    alerts = Alerts()

    raised = completion.alert_if_low(alerts, {"total": 100, "complete": 70, "ratio": 0.7}, date(2026, 10, 9), NOW)

    assert raised is True
    assert alerts.inserted[0]["source"] == "team_completion"
    assert "70" in alerts.inserted[0]["message"]


def test_a_repeat_within_a_day_is_not_raised_again():
    alerts = Alerts()
    alerts.open = {"ts": NOW - timedelta(hours=3)}

    assert completion.alert_if_low(alerts, {"total": 100, "complete": 70, "ratio": 0.7}, date(2026, 10, 9), NOW) is False
    assert alerts.inserted == []


def test_a_healthy_ratio_resolves_open_alerts():
    alerts = Alerts()

    assert completion.alert_if_low(alerts, {"total": 100, "complete": 95, "ratio": 0.95}, date(2026, 10, 9), NOW) is False
    assert alerts.updated and alerts.inserted == []


def test_a_tiny_batch_is_not_judged():
    alerts = Alerts()

    assert completion.alert_if_low(alerts, {"total": 5, "complete": 0, "ratio": 0.0}, date(2026, 10, 9), NOW) is False
    assert alerts.inserted == []
