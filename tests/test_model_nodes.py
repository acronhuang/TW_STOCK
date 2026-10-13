"""TDD: 模型到節點只有一份對照；換模型漏登記要在測試與開跑前就被擋下，而不是默默走到錯的節點。"""

import ast
import importlib
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from src.moe import consensus, model_nodes, preflight, role_router

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
N28 = "http://172.16.9.28:11434"
N27 = "http://172.16.9.27:11434"


def test_overrides_parse_and_strip_trailing_slash():
    parsed = model_nodes.parse_overrides("qwen3.5:9b=http://172.16.9.27:11435/, foo = https://h:1 ,,")
    assert parsed == {"qwen3.5:9b": "http://172.16.9.27:11435", "foo": "https://h:1"}
    assert model_nodes.parse_overrides("") == {}


@pytest.mark.parametrize("text", ["foo", "foo=", "=http://x:1", "foo=ftp://x", "a=http://x:1,b"])
def test_malformed_overrides_fail_loudly(text):
    with pytest.raises(ValueError):
        model_nodes.parse_overrides(text)


def test_unknown_model_raises_with_a_hint_instead_of_defaulting():
    with pytest.raises(model_nodes.UnregisteredModel) as info:
        model_nodes.node_of("mystery:1b")
    assert "mystery:1b" in str(info.value) and "model_nodes.py" in str(info.value)


def test_env_extends_the_table_without_touching_defaults():
    with patch.dict(os.environ, {"MODEL_NODES": "qwen3.5:9b=http://172.16.9.27:11435"}):
        reloaded = importlib.reload(model_nodes)
        try:
            assert reloaded.node_of("qwen3.5:9b") == "http://172.16.9.27:11435"
            assert reloaded.node_of("gemma2:9b") == reloaded.NODE_28
        finally:
            importlib.reload(model_nodes)


def test_default_nodes_match_where_the_models_actually_live():
    assert model_nodes.node_of("qwen3-14b:latest") == N28 and model_nodes.node_of("gemma2:9b") == N28
    assert model_nodes.node_of("qwen2.5-14b:latest") == N27 and model_nodes.node_of("llama3.1:8b") == N27
    assert model_nodes.node_of("bge-m3") == N28


def test_every_model_the_code_asks_for_is_registered():
    used = {
        *role_router.ROLE_TO_MODEL.values(),
        *consensus.COMMITTEE,
        consensus.FACILITATOR_MODEL,
        consensus.DEVIL_MODEL,
        model_nodes.ANSWER_MODEL,
        model_nodes.EMBED_MODEL,
    }
    assert not {m for m in used if m not in model_nodes.MODEL_NODES}, "換模型後要同步登記節點"


def test_roles_and_committee_use_the_shared_table():
    for model in set(role_router.ROLE_TO_MODEL.values()):
        assert role_router.MODEL_TO_URL[model] == model_nodes.MODEL_NODES[model]
    for model in {*consensus.COMMITTEE, consensus.DEVIL_MODEL}:
        assert consensus.COMMITTEE_MODEL_URL[model] == model_nodes.MODEL_NODES[model]


@pytest.mark.parametrize("model, node", [("gemma2:9b", N28), ("llama3.1:8b", N27)])
def test_facilitator_follows_its_model_unless_the_url_is_set(model, node):
    clean = {k: v for k, v in os.environ.items() if k not in {"OLLAMA_FACILITATOR_URL", "CONSENSUS_FACILITATOR"}}
    with patch.dict(os.environ, {**clean, "CONSENSUS_FACILITATOR": model}, clear=True):
        reloaded = importlib.reload(consensus)
        try:
            assert reloaded.FACILITATOR_URL == node
        finally:
            importlib.reload(consensus)


def test_answer_modules_take_model_and_node_from_the_table_not_literals():
    for rel in ("dashboard/pages/decision_qa.py", "scripts/stockrag_answer.py", "src/analysis/international_news.py"):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "model_nodes" in source, rel
        assert not re.search(r"^MODEL\s*=\s*[\"']", source, re.M), f"{rel} 又寫死了模型名"


def test_answer_endpoint_defaults_to_the_node_serving_the_answer_model():
    with patch.dict(os.environ, {}, clear=True):
        assert model_nodes.answer_url() == model_nodes.node_of(model_nodes.ANSWER_MODEL)
    with patch.dict(os.environ, {"RAG_OLLAMA_URL": "http://h:1/"}):
        assert model_nodes.answer_url() == "http://h:1"


def test_preflight_refuses_a_role_model_nobody_registered():
    with patch.dict(role_router.ROLE_TO_MODEL, {"technical-analyst": "mystery:1b"}):
        with pytest.raises(preflight.OllamaNotReady) as info:
            preflight.required_models(["technical-analyst"])
    assert "mystery:1b" in str(info.value)


def test_preflight_refuses_an_unregistered_committee_member():
    with patch.object(consensus, "COMMITTEE", ["gemma2:9b", "mystery:1b"]):
        with pytest.raises(preflight.OllamaNotReady):
            preflight.required_models(["technical-analyst"])


def test_preflight_can_include_the_answer_model_on_its_node():
    # 用一個委員與角色都沒用到的模型，才分得出有沒有把回答模型算進去。
    with patch.object(model_nodes, "ANSWER_MODEL", "bge-m3"):
        without = preflight.required_models(["technical-analyst"])
        with_aux = preflight.required_models(["technical-analyst"], include_aux=True)
    assert "bge-m3" not in set().union(*without.values())
    assert "bge-m3" in with_aux[model_nodes.NODE_28.rstrip("/")]


def test_embedding_endpoint_follows_the_embedding_model_unless_the_url_is_set():
    with patch.dict(os.environ, {}, clear=True):
        assert model_nodes.embed_url() == model_nodes.node_of(model_nodes.EMBED_MODEL)
        # 換成另一個節點上的模型，端點要跟著走
        with patch.object(model_nodes, "EMBED_MODEL", model_nodes.DEFAULT_TECH):
            assert model_nodes.embed_url() == N27
    with patch.dict(os.environ, {"RAG_EMBED_URL": "http://h:2/"}):
        assert model_nodes.embed_url() == "http://h:2"


_MODEL_NAME = re.compile(r"(?=.*[\d:])(qwen|gemma|llama|nomic|bge|granite|hermes|deepseek|mistral|phi|foundation|whiterabbit|lfm)[\w.\-]*(:[\w.\-]+)?", re.I)


def _docstring_nodes(tree):
    owners = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, owners) and node.body and isinstance(node.body[0], ast.Expr):
            value = node.body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.add(id(value))
    return found


def test_model_names_are_only_written_in_model_nodes():
    offenders = []
    for base in ("src", "scripts", "dashboard"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if path.name == "model_nodes.py" or "__pycache__" in path.parts or ".bak" in path.name:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            skip = _docstring_nodes(tree)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in skip:
                    continue
                parts = [p.strip() for p in node.value.split(",") if p.strip()]
                if parts and all(_MODEL_NAME.fullmatch(p) for p in parts):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.value!r}")
    assert not offenders, "模型名只能寫在 src/moe/model_nodes.py：\n" + "\n".join(offenders)


class _Tags:
    def __init__(self, names):
        self.names = names

    def raise_for_status(self):
        pass

    def json(self):
        return {"models": [{"name": n} for n in self.names]}


def _get(nodes):
    def get(url, timeout):
        base = url.removesuffix("/api/tags")
        if base not in nodes:
            raise ConnectionError(f"refused {base}")
        return _Tags(nodes[base])

    return get


def test_canonical_adds_latest_only_when_there_is_no_tag():
    assert model_nodes.canonical("bge-m3") == "bge-m3:latest"
    assert model_nodes.canonical("gemma2:9b") == "gemma2:9b"


def test_committee_check_matches_an_untagged_name_to_its_latest_tag():
    nodes = {N27: ["phi4:latest"]}
    assert consensus.missing_models(["phi4"], lambda m: N27, get=_get(nodes)) == []


def test_committee_check_only_looks_on_the_node_that_serves_the_model():
    nodes = {N27: ["a:1"], N28: ["b:1", "a:1"]}
    url_of = {"a:1": N27, "b:1": N27}.get
    assert consensus.missing_models(["a:1", "b:1"], url_of, get=_get(nodes)) == ["b:1"]


def test_committee_check_counts_an_unreachable_node_as_absent():
    url_of = {"a:1": N27, "b:1": N28}.get
    assert consensus.missing_models(["a:1", "b:1"], url_of, get=_get({N27: ["a:1"]})) == ["b:1"]


def test_committee_check_passes_when_everyone_is_where_they_belong():
    nodes = {N27: ["a:1"], N28: ["b:1"]}
    url_of = {"a:1": N27, "b:1": N28}.get
    assert consensus.missing_models(["a:1", "b:1"], url_of, get=_get(nodes)) == []
