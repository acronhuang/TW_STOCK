"""TDD: Hermes 回答的數字核對外掛——沒有出處的數字要被列出來，守門失效也要看得見。"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "deploy" / "hermes" / "twstock_guard" / "__init__.py"


def load(monkeypatch, repo=ROOT):
    monkeypatch.setenv("TWSTOCK_REPO", str(repo))
    spec = importlib.util.spec_from_file_location(f"twstock_guard_plugin_{id(monkeypatch)}", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin(monkeypatch):
    return load(monkeypatch)


TOOL = '{"symbol":"2330","current_price":2540.0,"dcf":{"fair_value":942.5,"upside_pct":-62.89}}'


def turn(plugin, question, tools, answer, session="s1", tool_session=None):
    plugin.on_pre_llm_call(session_id=session, user_message=question)
    for result in tools:
        plugin.on_post_tool_call(tool_name="stock_data", result=result, session_id=session if tool_session is None else tool_session)
    return plugin.on_transform_llm_output(response_text=answer, session_id=session)


def test_registers_exactly_the_three_hooks(plugin):
    seen = {}

    class Ctx:
        def register_hook(self, name, fn):
            seen[name] = fn

    plugin.register(Ctx())
    assert set(seen) == {"pre_llm_call", "post_tool_call", "transform_llm_output"}


def test_numbers_that_came_from_the_tool_pass_untouched(plugin):
    assert turn(plugin, "2330 估值？", [TOOL], "現價 2540.0，DCF 公平價 942.5，空間 -62.89%。") is None


def test_an_invented_number_is_listed_and_the_answer_is_kept(plugin):
    out = turn(plugin, "2330 估值？", [TOOL], "現價 2540.0，三年後目標價 3810.5。")
    assert out.startswith("現價 2540.0，三年後目標價 3810.5。")
    assert "找不到出處" in out and "3810.5" in out and "2540.0" not in out.split("找不到出處")[1]


def test_a_number_only_in_the_question_is_not_flagged(plugin):
    assert turn(plugin, "如果買 1500.5 元呢？", [TOOL], "你提到的 1500.5 元低於現價 2540.0。") is None


def test_figures_without_any_tool_call_are_flagged(plugin):
    out = turn(plugin, "你好", [], "台積電現價 2540.0 元。")
    assert out and "2540.0" in out.split("找不到出處")[1]


def test_small_counts_are_not_checked_like_the_project_guard(plugin):
    assert turn(plugin, "有哪些？", [TOOL], "共 3 項，前 2 項較佳。") is None


def test_tool_results_of_an_earlier_turn_do_not_support_the_next_answer(plugin):
    assert turn(plugin, "2330？", [TOOL], "現價 2540.0。", session="s1") is None
    plugin.on_pre_llm_call(session_id="s1", user_message="再說一次")
    out = plugin.on_transform_llm_output(response_text="現價 2540.0。", session_id="s1")
    assert out and "2540.0" in out.split("找不到出處")[1]


def test_a_turn_that_never_finished_does_not_support_the_next_one(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="2330？")
    plugin.on_post_tool_call(tool_name="stock_data", result=TOOL, session_id="s1")
    plugin.on_pre_llm_call(session_id="s1", user_message="換個問題")
    out = plugin.on_transform_llm_output(response_text="現價 2540.0。", session_id="s1")
    assert out and "2540.0" in out.split("找不到出處")[1]


def test_state_is_cleared_after_the_answer(plugin):
    turn(plugin, "2330？", [TOOL], "現價 2540.0。")
    out = plugin.on_transform_llm_output(response_text="現價 2540.0。", session_id="s1")
    assert out and "2540.0" in out.split("找不到出處")[1]


def test_a_tool_call_reported_under_another_session_id_still_counts_for_the_current_turn(plugin):
    assert turn(plugin, "2330？", [TOOL], "現價 2540.0。", session="s1", tool_session="") is None


def test_multimodal_user_message_is_flattened(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message=[{"type": "text", "text": "目標價 1500.5"}, {"type": "image"}])
    assert plugin.on_transform_llm_output(response_text="你說的 1500.5 沒有資料。", session_id="s1") is None


def test_empty_answers_are_left_alone(plugin):
    assert plugin.on_transform_llm_output(response_text="", session_id="s1") is None


def test_hooks_never_raise_on_odd_input(plugin):
    assert plugin.on_pre_llm_call(session_id=None, user_message=None) is None
    assert plugin.on_post_tool_call(tool_name="x", result=None, session_id=None) is None


def test_old_turns_are_dropped_so_memory_stays_bounded(plugin):
    for i in range(plugin._MAX_TURNS + 20):
        plugin.on_pre_llm_call(session_id=f"s{i}", user_message="q")
    assert len(plugin._turns) == plugin._MAX_TURNS


def test_when_the_guard_cannot_load_the_answer_says_so_instead_of_passing_silently(monkeypatch, tmp_path):
    broken = load(monkeypatch, repo=tmp_path)
    out = turn(broken, "2330？", [TOOL], "現價 2540.0。")
    assert out.startswith("現價 2540.0。") and "數字核對未執行" in out
