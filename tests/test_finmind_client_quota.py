"""TDD: FinMind 客戶端遇到 HTTP 402 不重試，連續兩次後略過本程序剩下的請求，成功一次就清掉計數；其他錯誤仍照舊重試。"""

import logging

import pytest

from src.downloaders import finmind_client as fc

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, ""

    def json(self):
        return self._payload


def ok_payload():
    return FakeResponse(200, {"status": 200, "data": [{"stock_id": "1101", "value": 1}]})


@pytest.fixture
def wired(monkeypatch):
    sleeps, calls, queue = [], [], []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["dataset"])
        return queue.pop(0)

    monkeypatch.setattr(fc.requests, "get", fake_get)
    monkeypatch.setattr(fc.time, "sleep", lambda s: sleeps.append(s))
    client = fc.FinMindClient("token", logging.getLogger("test"))
    return client, calls, sleeps, queue


def test_a_402_is_not_retried_and_does_not_wait(wired):
    client, calls, sleeps, queue = wired
    queue += [FakeResponse(402)]

    assert client.fetch_data("TaiwanStockInfo", {}) == []
    assert len(calls) == 1 and sleeps == []


def test_after_two_consecutive_402s_the_remaining_requests_are_not_sent(wired):
    client, calls, _, queue = wired
    queue += [FakeResponse(402), FakeResponse(402)]

    client.fetch_data("A", {})
    client.fetch_data("B", {})
    assert client.fetch_data("C", {}) == [] and client.fetch_data("D", {}) == []

    assert calls == ["A", "B"]


def test_a_success_between_two_402s_resets_the_streak(wired):
    client, calls, _, queue = wired
    queue += [FakeResponse(402), ok_payload(), FakeResponse(402), ok_payload()]

    client.fetch_data("A", {})
    assert client.fetch_data("B", {}) != []
    client.fetch_data("C", {})
    assert client.fetch_data("D", {}) != [] and calls == ["A", "B", "C", "D"]


def test_the_log_line_still_contains_the_string_the_quota_check_looks_for(wired, caplog):
    client, _, _, queue = wired
    queue += [FakeResponse(402)]

    with caplog.at_level(logging.ERROR, logger="test"):
        client.fetch_data("A", {})

    assert "HTTP 錯誤: 402" in caplog.text


def test_other_server_errors_are_still_retried_with_backoff(wired):
    client, calls, sleeps, queue = wired
    queue += [FakeResponse(500)] * 4

    assert client.fetch_data("A", {}) == []

    assert len(calls) == 4 and sleeps == [2, 4, 8]
