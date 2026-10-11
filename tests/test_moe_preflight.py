"""TDD: Ollama 是硬性前提——節點或模型缺席時必須在開跑前就停下來，而不是逐檔寫出假結論。"""

import pytest

from src.moe import preflight

pytestmark = pytest.mark.unit

N28 = "http://172.16.9.28:11434"
N27 = "http://172.16.9.27:11434"


class Response:
    def __init__(self, names):
        self.names = names

    def raise_for_status(self):
        pass

    def json(self):
        return {"models": [{"name": name} for name in self.names]}


def getter(nodes):
    def get(url, timeout):
        base = url.removesuffix("/api/tags")
        if base not in nodes:
            raise ConnectionError(f"refused {base}")
        return Response(nodes[base])

    return get


REQUIRED = {N28: {"qwen3-14b:latest", "gemma2:9b"}, N27: {"llama3.1:8b"}}


def test_a_ready_cluster_has_no_problems():
    nodes = {N28: ["qwen3-14b:latest", "gemma2:9b", "x"], N27: ["llama3.1:8b"]}

    assert preflight.check_ollama(REQUIRED, get=getter(nodes)) == []


def test_an_unreachable_node_is_reported_by_address():
    problems = preflight.check_ollama(REQUIRED, get=getter({N28: ["qwen3-14b:latest", "gemma2:9b"]}))

    assert len(problems) == 1
    assert N27 in problems[0]


def test_a_missing_model_is_reported_with_its_node():
    nodes = {N28: ["qwen3-14b:latest"], N27: ["llama3.1:8b"]}

    problems = preflight.check_ollama(REQUIRED, get=getter(nodes))

    assert len(problems) == 1
    assert "gemma2:9b" in problems[0] and N28 in problems[0]


def test_every_failing_node_is_listed_not_just_the_first():
    assert len(preflight.check_ollama(REQUIRED, get=getter({}))) == 2


def test_ensure_ready_raises_with_all_problems():
    with pytest.raises(preflight.OllamaNotReady) as error:
        preflight.ensure_ready(REQUIRED, get=getter({}))

    assert N28 in str(error.value) and N27 in str(error.value)


def test_ensure_ready_passes_silently_when_ready():
    nodes = {N28: ["qwen3-14b:latest", "gemma2:9b"], N27: ["llama3.1:8b"]}

    preflight.ensure_ready(REQUIRED, get=getter(nodes))


def test_required_models_cover_roles_committee_and_facilitator_per_node():
    from src.moe import consensus, role_router

    required = preflight.required_models(["technical-analyst", "risk-manager"])

    expected_role_models = {role_router.ROLE_TO_MODEL["technical-analyst"], role_router.ROLE_TO_MODEL["risk-manager"]}
    all_models = set().union(*required.values())
    assert expected_role_models <= all_models
    assert set(consensus.COMMITTEE) <= all_models
    assert consensus.FACILITATOR_MODEL in required[consensus.FACILITATOR_URL.rstrip("/")]


def test_a_model_is_required_on_the_node_that_actually_serves_it():
    from src.moe import role_router

    required = preflight.required_models(["technical-analyst"])
    model = role_router.ROLE_TO_MODEL["technical-analyst"]
    node = role_router.MODEL_TO_URL.get(model, role_router.OLLAMA_URL).rstrip("/")

    assert model in required[node]
