"""TDD: Hermes 用前卸載擋路模型——只在會造成部分載入時才動，失敗不能擋住對話。"""

import importlib.util
from pathlib import Path

import pytest

from src.moe import model_nodes
from src.ops import hermes_gpu_room as room

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "deploy" / "hermes" / "twstock_guard" / "__init__.py"
H = "hermes-qwen3-4b:latest"
G = "gemma4:12b-it-q4_K_M"
Q = "qwen3.8:27b-q4_K_M"


def m(name, size, vram):
    return {"name": name, "size": size, "size_vram": vram}


def test_nothing_to_do_without_a_blocker():
    assert room.plan([m(Q, 17, 17), m(H, 12, 4)], H, [G]) == []


def test_hermes_not_loaded_and_blocker_loaded_unloads_only_the_blocker():
    assert room.plan([m(Q, 17, 17), m(G, 9, 9)], H, [G]) == [G]


def test_hermes_fully_loaded_is_left_alone():
    assert room.plan([m(G, 9, 9), m(H, 12, 12)], H, [G]) == []


def test_partial_hermes_is_unloaded_with_the_blocker():
    assert room.plan([m(G, 9, 9), m(H, 12, 4)], H, [G]) == [G, H]


def test_only_listed_models_are_ever_evicted():
    assert Q not in room.plan([m(Q, 17, 17), m(G, 9, 9)], H, [G])


class Fake:
    def __init__(self, states):
        self.states, self.unloaded, self.slept = list(states), [], 0

    def fetch(self, url):
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def unload(self, url, model):
        self.unloaded.append((url, model))

    def sleep(self, seconds):
        self.slept += 1


def run(fake, **kw):
    return room.make_room("http://x", H, [G], fetch=fake.fetch, unload=fake.unload, sleep=fake.sleep, **kw)


def test_make_room_unloads_then_waits_until_gone():
    fake = Fake([[m(G, 9, 9)], [m(G, 9, 9)], []])
    assert run(fake) == [G]
    assert fake.unloaded == [("http://x", G)]
    assert fake.slept == 1


def test_make_room_does_not_call_unload_when_plan_is_empty():
    fake = Fake([[m(H, 12, 12)]])
    assert run(fake) == []
    assert fake.unloaded == []


def test_make_room_times_out_loudly_when_model_stays_loaded():
    fake = Fake([[m(G, 9, 9)]])
    with pytest.raises(TimeoutError):
        run(fake, wait_s=2.0, poll_s=0.5)
    assert fake.slept == 4


def test_make_room_unloads_blocker_and_partial_hermes_together():
    fake = Fake([[m(G, 9, 9), m(H, 12, 4)], []])
    assert run(fake) == [G, H]
    assert fake.unloaded == [("http://x", G), ("http://x", H)]


def test_only_a_committee_seat_is_ever_evicted_for_hermes():
    critical = {model_nodes.DEFAULT_RISK, model_nodes.DEFAULT_MAIN, model_nodes.DEFAULT_EMBED, model_nodes.ANSWER_MODEL}
    assert not critical & set(model_nodes.HERMES_EVICT)
    assert set(model_nodes.HERMES_EVICT) <= set(model_nodes.DEFAULT_COMMITTEE)


def test_nodes_hermes_evicts_are_registered_on_hermes_node():
    assert model_nodes.HERMES_EVICT
    for name in model_nodes.HERMES_EVICT:
        assert model_nodes.node_of(name) == model_nodes.HERMES_URL


def test_hermes_model_is_not_evicted():
    assert model_nodes.canonical(model_nodes.HERMES_MODEL) not in map(model_nodes.canonical, model_nodes.HERMES_EVICT)


def load_plugin(monkeypatch):
    monkeypatch.setenv("TWSTOCK_REPO", str(ROOT))
    spec = importlib.util.spec_from_file_location(f"twstock_guard_room_{id(monkeypatch)}", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._prefetch = lambda question: ([], "")
    return module


def test_plugin_calls_make_room_before_each_turn(monkeypatch):
    plugin = load_plugin(monkeypatch)
    calls = []
    plugin._make_room = lambda: calls.append(1) or []
    plugin.on_pre_llm_call(session_id="s", user_message="hi")
    assert calls == [1]


def test_plugin_survives_make_room_failure_and_says_so(monkeypatch, capsys):
    plugin = load_plugin(monkeypatch)

    def boom():
        raise OSError("ollama down")

    plugin._make_room = boom
    plugin.on_pre_llm_call(session_id="s", user_message="hi")
    assert "ollama down" in capsys.readouterr().err
    assert plugin._turns["s"]["question"] == "hi"


def test_plugin_make_room_uses_node_settings(monkeypatch):
    plugin = load_plugin(monkeypatch)
    seen = {}
    monkeypatch.setattr(room, "make_room", lambda url, hermes, evict, **kw: seen.update(url=url, hermes=hermes, evict=evict) or [])
    plugin._module = lambda path, label: {"nodes": model_nodes, "room": room}[label]
    plugin._make_room()
    assert seen["url"] == model_nodes.HERMES_URL
    assert seen["hermes"] == model_nodes.canonical(model_nodes.HERMES_MODEL)
    assert seen["evict"] == [model_nodes.canonical(n) for n in model_nodes.HERMES_EVICT]


def test_plugin_canonicalizes_untagged_evict_names(monkeypatch):
    plugin = load_plugin(monkeypatch)
    seen = {}
    monkeypatch.setattr(room, "make_room", lambda url, hermes, evict, **kw: seen.update(evict=evict) or [])
    monkeypatch.setattr(model_nodes, "HERMES_EVICT", ("bge-m3",))
    plugin._module = lambda path, label: {"nodes": model_nodes, "room": room}[label]
    plugin._make_room()
    assert seen["evict"] == ["bge-m3:latest"]


def test_hermes_evict_is_derived_from_the_committee_members_on_the_hermes_node():
    nodes = {"a": "http://x:1", "b": "http://x:1/", "c": "http://y:1", "d": "http://x:1"}
    assert model_nodes.hermes_evict(("a", "b", "c", "d", "e"), nodes, "http://x:1", {"a"}) == ("b", "d")


def test_hermes_evict_never_includes_a_model_other_roles_need():
    nodes = {"risk": "http://x:1", "seat": "http://x:1"}
    assert model_nodes.hermes_evict(("risk", "seat"), nodes, "http://x:1", {"risk"}) == ("seat",)


def test_the_effective_committee_follows_the_environment_like_the_consensus_module(monkeypatch):
    monkeypatch.delenv("CONSENSUS_MODELS", raising=False)
    assert model_nodes.effective_committee() == tuple(model_nodes.DEFAULT_COMMITTEE)
    monkeypatch.setenv("CONSENSUS_MODELS", " m1 , m2,,")
    assert model_nodes.effective_committee() == ("m1", "m2")


def test_the_current_evict_list_is_the_gemma_seat_on_node_27():
    assert model_nodes.HERMES_EVICT == (model_nodes.DEFAULT_MEMBER_GOOGLE,)
