"""fetch_tpex 遇到被截斷的檔案要重試，不可直接放棄整個上櫃行情。"""
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import twse_daily_update as tdu  # noqa: E402


class FakeResp:
    def __init__(self, body: bytes, declared: int | None = None):
        self.content = body
        self.headers = {"Content-Length": str(len(body) if declared is None else declared)}

    def raise_for_status(self):
        pass

    def json(self):
        import json
        return json.loads(self.content)


GOOD = b'[{"Date": "1151012", "SecuritiesCompanyCode": "1264"}]'


def patch_get(monkeypatch, responses):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(tdu.requests, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return calls


def test_truncated_then_complete_retries(monkeypatch):
    calls = patch_get(monkeypatch, [FakeResp(GOOD[:20], declared=len(GOOD)), FakeResp(GOOD)])
    assert tdu._get_tpex_json("u")[0]["SecuritiesCompanyCode"] == "1264"
    assert len(calls) == 2


def test_invalid_json_without_length_header_retries(monkeypatch):
    bad = FakeResp(b'[{"Date": "11510')
    del bad.headers["Content-Length"]
    calls = patch_get(monkeypatch, [bad, FakeResp(GOOD)])
    assert len(tdu._get_tpex_json("u")) == 1
    assert len(calls) == 2


def test_network_error_retries(monkeypatch):
    calls = patch_get(monkeypatch, [requests.ConnectionError("x"), FakeResp(GOOD)])
    assert len(tdu._get_tpex_json("u")) == 1
    assert len(calls) == 2


def test_gives_up_after_all_attempts(monkeypatch):
    calls = patch_get(monkeypatch, [FakeResp(GOOD[:10], declared=len(GOOD)) for _ in range(3)])
    with pytest.raises(ValueError):
        tdu._get_tpex_json("u", attempts=3)
    assert len(calls) == 3