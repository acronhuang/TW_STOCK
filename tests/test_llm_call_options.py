"""TDD: Ollama 呼叫的固定選項——關閉思考、限制輸出長度、明確指定上下文，撞到上限要看得見。"""

import ast
import json
from pathlib import Path

import pytest

from scripts import stockrag_ingest, stockrag_search
from src.moe import consensus, role_router

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


@pytest.fixture
def posted(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse({"response": "文字", "done_reason": "stop"})

    monkeypatch.setattr(role_router.requests, "post", fake_post)
    monkeypatch.setattr(consensus.requests, "post", fake_post)
    for name in ("ROLE_THINK", "ROLE_NUM_PREDICT", "ROLE_NUM_CTX", "CONSENSUS_THINK", "CONSENSUS_NUM_PREDICT", "CONSENSUS_NUM_CTX"):
        monkeypatch.delenv(name, raising=False)
    return calls


def test_a_role_call_turns_thinking_off_and_caps_the_output_and_fixes_the_context(posted):
    role_router.ask_role("fundamental-analyst", "問題")

    body = posted[0]["json"]
    assert body["think"] is False and body["stream"] is False
    assert body["options"]["num_ctx"] == 8192 and body["options"]["num_predict"] == 1536
    assert body["options"]["temperature"] == 0 and body["options"]["seed"] == 42 and body["options"]["num_gpu"] == 99


@pytest.mark.parametrize("role", list(role_router.ROLE_TO_MODEL))
def test_every_role_gets_the_same_safe_options(posted, role):
    role_router.ask_role(role, "問題")

    assert posted[0]["json"]["think"] is False and posted[0]["json"]["options"]["num_predict"] == 1536


def test_the_role_options_can_be_changed_from_the_environment(posted, monkeypatch):
    monkeypatch.setenv("ROLE_THINK", "true")
    monkeypatch.setenv("ROLE_NUM_PREDICT", "300")
    monkeypatch.setenv("ROLE_NUM_CTX", "4096")
    role_router.ask_role("macro-analyst", "問題")

    body = posted[0]["json"]
    assert body["think"] is True and body["options"]["num_predict"] == 300 and body["options"]["num_ctx"] == 4096


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False), ("", False), ("no", False)])
def test_the_thinking_switch_reads_common_truthy_words(posted, monkeypatch, value, expected):
    monkeypatch.setenv("ROLE_THINK", value)
    role_router.ask_role("macro-analyst", "問題")

    assert posted[0]["json"]["think"] is expected


def test_a_report_that_hit_the_output_cap_is_flagged_but_keeps_its_text(monkeypatch):
    monkeypatch.setattr(role_router.requests, "post", lambda *a, **k: FakeResponse({"response": "寫到一半", "done_reason": "length"}))

    out = role_router.ask_role("macro-analyst", "問題")

    assert out["response"] == "寫到一半" and out["truncated"] is True and "error" not in out


def test_a_complete_report_has_no_truncated_flag(posted):
    assert "truncated" not in role_router.ask_role("macro-analyst", "問題")


def test_a_response_without_a_done_reason_is_not_flagged(monkeypatch):
    monkeypatch.setattr(role_router.requests, "post", lambda *a, **k: FakeResponse({"response": "文字"}))

    assert "truncated" not in role_router.ask_role("macro-analyst", "問題")


def test_a_committee_or_facilitator_call_has_the_same_protections(posted):
    consensus._ask("qwen3-14b:latest", "提示", 30)

    body = posted[0]["json"]
    assert body["think"] is False and body["options"]["num_ctx"] == 8192 and body["options"]["num_predict"] == 768


def test_the_committee_options_can_be_changed_from_the_environment(posted, monkeypatch):
    monkeypatch.setenv("CONSENSUS_THINK", "1")
    monkeypatch.setenv("CONSENSUS_NUM_PREDICT", "200")
    consensus._ask("gemma2:9b", "提示", 30)

    assert posted[0]["json"]["think"] is True and posted[0]["json"]["options"]["num_predict"] == 200


class FakeUrlResponse:
    def __init__(self, vector):
        self.vector = vector

    def read(self):
        return json.dumps({"embedding": self.vector}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("module, dim", [(stockrag_search, 3), (stockrag_ingest, stockrag_ingest.DIM)])
def test_embedding_requests_state_the_context_instead_of_relying_on_the_server_default(monkeypatch, module, dim):
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(json.loads(request.data))
        return FakeUrlResponse([0.1] * dim)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    module.embed("文字")

    assert seen[0]["options"] == {"num_ctx": 8192} and seen[0]["prompt"] == "文字"


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("rel", ["src/analysis/international_news.py", "scripts/stockrag_answer.py", "dashboard/pages/decision_qa.py"])
def test_answer_model_requests_turn_thinking_off(rel):
    # qwen3.8 預設會思考，輸出上限 700~800 會被思考吃光而回空白。
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    payloads = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)
                and {"model", "options"} <= {k.value for k in n.keys if isinstance(k, ast.Constant)}]
    assert payloads, rel
    for node in payloads:
        pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        assert isinstance(pairs.get("think"), ast.Constant) and pairs["think"].value is False, rel
