"""TDD: 記錄 FinMind 伺服器端用量；查不到時記「無資料」，不得記成 0。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

from src.ops import finmind_usage

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent


class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code, self._payload, self._bad_json = status, payload, bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def getter(response=None, error=None):
    calls = []

    def get(url, params=None, timeout=None):
        calls.append((url, params, timeout))
        if error:
            raise error
        return response

    get.calls = calls
    return get


def ok(used, limit=600):
    return FakeResponse(200, {"status": 200, "user_count": used, "api_request_limit": limit})


def test_server_reports_usage():
    assert finmind_usage.fetch_usage("tok", get=getter(ok(301))) == (301, 600)
    assert finmind_usage.describe((301, 600)) == "伺服器端用量 301/600"


def test_a_real_zero_is_reported_as_zero():
    usage = finmind_usage.fetch_usage("tok", get=getter(ok(0)))
    assert usage == (0, 600)
    assert finmind_usage.describe(usage) == "伺服器端用量 0/600"


@pytest.mark.parametrize(
    "get",
    [
        getter(error=requests.Timeout("slow")),
        getter(error=requests.ConnectionError("down")),
        getter(FakeResponse(500, {})),
        getter(FakeResponse(200, {"status": 400, "msg": "Token 違法."})),
        getter(FakeResponse(200, {"status": 400, "user_count": 5, "api_request_limit": 600})),
        getter(FakeResponse(500, {"status": 200, "user_count": 5, "api_request_limit": 600})),
        getter(FakeResponse(200, {"status": 200, "user_count": True, "api_request_limit": 600})),
        getter(FakeResponse(200, bad_json=True)),
        getter(FakeResponse(200, {"status": 200, "api_request_limit": 600})),
        getter(FakeResponse(200, {"status": 200, "user_count": 5})),
        getter(FakeResponse(200, {"status": 200, "user_count": "5", "api_request_limit": 600})),
        getter(FakeResponse(200, {"status": 200, "user_count": 5, "api_request_limit": 0})),
    ],
    ids=["timeout", "connection", "http500", "bad-token", "status400-with-count", "http500-with-count", "bool-count", "not-json", "no-count", "no-limit", "string-count", "zero-limit"],
)
def test_any_failure_is_no_data_never_zero(get):
    usage = finmind_usage.fetch_usage("tok", get=get)
    assert usage is None
    text = finmind_usage.describe(usage)
    assert text == "伺服器端用量無資料"
    assert "0" not in text and "%" not in text


def test_no_token_means_no_data_and_no_request():
    get = getter(ok(1))
    assert finmind_usage.fetch_usage("", get=get) is None
    assert get.calls == []


def test_token_is_sent_as_a_parameter_with_a_timeout():
    get = getter(ok(1))
    finmind_usage.fetch_usage("tok", get=get)
    url, params, timeout = get.calls[0]
    assert url == finmind_usage.URL and params == {"token": "tok"} and timeout


def test_script_prints_no_data_and_exits_zero_without_a_token():
    env = {k: v for k, v in os.environ.items() if k != "FINMIND_API_TOKEN"}
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "log_finmind_usage.py"), "開始"],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=30,
    )
    assert done.returncode == 0
    assert done.stdout.strip() == "FinMind 伺服器端用量無資料（開始）"
