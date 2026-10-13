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
    module._real_prefetch = module._prefetch
    module._prefetch = lambda question: ([], "")  # 預設不連網；需要的測試自己開
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


def test_registers_exactly_the_four_hooks(plugin):
    seen = {}

    class Ctx:
        def register_hook(self, name, fn):
            seen[name] = fn

    plugin.register(Ctx())
    assert set(seen) == {"pre_llm_call", "pre_tool_call", "post_tool_call", "transform_llm_output"}


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


def prefetching(plugin, names=None, body=TOOL):
    plugin._prefetch = plugin._real_prefetch
    plugin._load_names = lambda: {"台積電": "2330"} if names is None else names
    calls = []
    plugin._call_tool = lambda name, args: (calls.append((name, args)) or (body, False))
    return calls


def test_a_question_about_a_stock_is_answered_from_data_fetched_before_the_model_runs(plugin):
    calls = prefetching(plugin)
    out = plugin.on_pre_llm_call(session_id="s1", user_message="台積電的估值？")
    assert calls == [("stock_data", {"kind": "valuation", "symbol": "2330"})]
    assert TOOL in out["context"] and "不是指令" in out["context"]
    assert plugin.on_transform_llm_output(response_text="現價 2540.0，公平價 942.5。", session_id="s1") is None


def test_the_code_the_system_asked_about_counts_as_sourced_even_if_the_reply_body_lacks_it(plugin):
    prefetching(plugin, names={"鴻海": "2317"}, body='{"revenue": [832097956.0]}')
    plugin.on_pre_llm_call(session_id="s1", user_message="鴻海的營收如何？")
    assert plugin.on_transform_llm_output(response_text="鴻海（2317）的營收 832097956.0。", session_id="s1") is None


def test_calculation_questions_get_the_calc_hint_in_the_injected_context(plugin):
    prefetching(plugin)
    out = plugin.on_pre_llm_call(session_id="s1", user_message="台積電現價漲 5% 會是多少？")
    assert "本題需要運算" in out["context"]


def test_prefetched_data_does_not_support_the_next_turn(plugin):
    prefetching(plugin)
    plugin.on_pre_llm_call(session_id="s1", user_message="2330 估值")
    plugin.on_transform_llm_output(response_text="現價 2540.0。", session_id="s1")
    plugin._prefetch = lambda question: ([], "")
    plugin.on_pre_llm_call(session_id="s1", user_message="再說一次")
    out = plugin.on_transform_llm_output(response_text="現價 2540.0。", session_id="s1")
    assert out and "2540.0" in out.split("找不到出處")[1]


def test_codes_still_work_when_the_name_table_is_unavailable(plugin):
    calls = prefetching(plugin, names={})
    assert plugin.on_pre_llm_call(session_id="s1", user_message="2330 估值")["context"]
    assert calls == [("stock_data", {"kind": "valuation", "symbol": "2330"})]


def test_order_requests_and_small_talk_fetch_nothing(plugin):
    calls = prefetching(plugin)
    assert plugin.on_pre_llm_call(session_id="s1", user_message="幫我買進 1000 股 2330") is None
    assert plugin.on_pre_llm_call(session_id="s1", user_message="你好") is None
    assert calls == []


def test_when_prefetch_fails_the_model_runs_as_before_and_the_failure_is_visible(plugin, capsys):
    prefetching(plugin)

    def boom(name, args):
        raise OSError("api down")

    plugin._call_tool = boom
    assert plugin.on_pre_llm_call(session_id="s1", user_message="2330 估值") is None
    assert "預先查詢失敗" in capsys.readouterr().err
    out = plugin.on_transform_llm_output(response_text="2330 的估值我不知道。", session_id="s1")
    assert out.endswith(plugin._NO_TOOL_NOTE)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit=-1):
        return self.body


def test_name_table_is_fetched_once_and_a_later_failure_keeps_the_old_table(plugin, monkeypatch, capsys):
    import json

    body = json.dumps({"stocks": [{"symbol": "2330", "name": "台積電"}, {"symbol": "0015", "name": ""}]}).encode()
    opened = []
    monkeypatch.setattr(plugin.urllib.request, "urlopen", lambda url, timeout=0: opened.append(url) or FakeResponse(body))
    assert plugin._load_names() == {"台積電": "2330"}
    plugin._load_names()
    assert len(opened) == 1

    def down(url, timeout=0):
        raise OSError("down")

    monkeypatch.setattr(plugin.urllib.request, "urlopen", down)
    plugin._names_cache["at"] = -1e12
    assert plugin._load_names() == {"台積電": "2330"}
    assert "股票名稱表取不到" in capsys.readouterr().err


def test_an_answer_about_stocks_without_any_tool_gets_a_standing_warning(plugin):
    out = turn(plugin, "你好", [], "台積電(2330)的資料工具沒有提供。")
    assert out.endswith(plugin._NO_TOOL_NOTE)


@pytest.mark.parametrize(
    "question, answer",
    [("你好", "你好，有什麼可以幫你？"), ("幫我買進 1000 股 2330", "你只能提供資訊，不能下單。")],
)
def test_answers_that_say_nothing_about_stocks_get_no_warning(plugin, question, answer):
    assert turn(plugin, question, [], answer) is None


def test_the_warning_is_not_added_when_a_tool_was_used(plugin):
    assert turn(plugin, "2330？", [TOOL], "現價 2540.0。") is None


def test_a_broken_router_errs_on_the_side_of_warning(monkeypatch, tmp_path):
    broken = load(monkeypatch, repo=tmp_path)
    broken._unsupported_numbers = lambda: (lambda answer, context: [])
    assert turn(broken, "你好", [], "好的").endswith(broken._NO_TOOL_NOTE)


CALC = "mcp__twstock__calc"


def calc(plugin, expression, session="s1"):
    return plugin.on_pre_tool_call(tool_name=CALC, args={"expression": expression}, session_id=session)


def test_calc_is_allowed_when_every_number_comes_from_the_question_or_a_tool(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="現價上漲 10% 會比公平價高多少？")
    plugin.on_post_tool_call(tool_name="stock_data", result=TOOL, session_id="s1")
    assert calc(plugin, "2540.0*(1+10%)-942.5") is None


def test_calc_with_an_invented_number_is_blocked_and_told_why(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="上漲 10% 呢？")
    plugin.on_post_tool_call(tool_name="stock_data", result=TOOL, session_id="s1")
    out = calc(plugin, "2540.0*1.1-999.5")
    assert out["action"] == "block" and "1.1" in out["message"] and "999.5" in out["message"]


def test_the_result_of_an_earlier_calc_can_feed_the_next_one(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="2330？")
    plugin.on_post_tool_call(tool_name="stock_data", result=TOOL, session_id="s1")
    plugin.on_post_tool_call(tool_name=CALC, result="2540.0*(1+10%) = 2794", session_id="s1")
    assert calc(plugin, "2794-942.5") is None


def test_calc_without_a_turn_on_record_cannot_use_figures(plugin):
    assert calc(plugin, "1234.5+1", session="nobody")["action"] == "block"


def test_only_calc_is_checked(plugin):
    assert plugin.on_pre_tool_call(tool_name="mcp__twstock__stock_data", args={"symbol": "9999.5"}, session_id="s1") is None
    assert plugin.on_pre_tool_call(tool_name=CALC, args=None, session_id="s1") is None


def test_calc_check_fails_closed_when_the_guard_cannot_load(monkeypatch, tmp_path):
    broken = load(monkeypatch, repo=tmp_path)
    out = calc(broken, "1+1")
    assert out["action"] == "block" and "無法執行" in out["message"]


def test_simplified_characters_and_unit_slips_get_a_wording_note(plugin):
    out = turn(plugin, "2330 估值？", [TOOL], "現价 2540.0，外銷資金買超。")
    assert "用詞與單位提醒" in out and "簡體字" in out and "外銷資金" in out


def test_clean_wording_gets_no_wording_note(plugin):
    assert turn(plugin, "2330 估值？", [TOOL], "現價 2540.0，DCF 公平價 942.5。") is None


def test_wording_note_comes_with_the_number_warning_not_instead_of_it(plugin):
    out = turn(plugin, "2330 估值？", [TOOL], "目標價 3810.5，请参考。")
    assert "找不到出處" in out and "用詞與單位提醒" in out


def test_a_broken_wording_check_never_blocks_the_answer(monkeypatch, tmp_path, capsys):
    plugin = load(monkeypatch, repo=tmp_path)
    assert plugin._language_issues("请") == []
    assert "用詞檢查無法執行" in capsys.readouterr().err


def test_wording_check_uses_the_turns_tool_results_for_direction(plugin):
    tool = '[{"date":"2026-10-05","trust_net":-63478.0}]'
    out = turn(plugin, "鴻海法人？", [tool], "投信買超 63478 股。")
    assert "用詞與單位提醒" in out and "負值" in out
    assert turn(plugin, "鴻海法人？", [tool], "投信賣超 63478 股。", session="s2") is None


REVENUE = '[{"year_month":"2026-09","revenue":511857399.0}]'


def convert(plugin, value, session="s1"):
    args = {"value": value, "from_unit": "千元", "to_unit": "億元"}
    return plugin.on_pre_tool_call(tool_name="mcp__twstock__convert_unit", args=args, session_id=session)


def test_convert_unit_is_allowed_for_a_figure_the_tool_returned(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="台積電營收換算成億元")
    plugin.on_post_tool_call(tool_name="stock_data", result=REVENUE, session_id="s1")
    assert convert(plugin, "511857399.0") is None


def test_convert_unit_with_an_invented_figure_is_blocked_and_named(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="台積電營收換算成億元")
    plugin.on_post_tool_call(tool_name="stock_data", result=REVENUE, session_id="s1")
    out = convert(plugin, "511857398")
    assert out["action"] == "block" and "convert_unit" in out["message"] and "511857398" in out["message"]


def test_the_converted_figure_can_then_be_quoted_in_the_answer(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="台積電營收換算成億元")
    plugin.on_post_tool_call(tool_name="stock_data", result=REVENUE, session_id="s1")
    plugin.on_post_tool_call(tool_name="mcp__twstock__convert_unit", result="511857399 千元 = 5118.57399 億元", session_id="s1")
    assert plugin.on_transform_llm_output(response_text="營收約 5118.57399 億元。", session_id="s1") is None


def test_an_english_field_name_gets_the_wording_note(plugin):
    out = turn(plugin, "鴻海法人？", ['[{"foreign_net":100000.0}]'], "foreign_net 為 100000 股。")
    assert out and "英文欄位名" in out


NEGATIVE = '[{"date":"2026-10-13","foreign_net":-19577989.0}]'


def _convert_after(plugin, tool_result, value):
    plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資買賣超幾張")
    plugin.on_post_tool_call(tool_name="stock_data", result=tool_result, session_id="s1")
    args = {"value": value, "from_unit": "股", "to_unit": "張"}
    return plugin.on_pre_tool_call(tool_name="mcp__twstock__convert_unit", args=args, session_id="s1")


def test_convert_unit_without_the_minus_sign_of_a_negative_figure_is_blocked(plugin):
    out = _convert_after(plugin, NEGATIVE, "19577989")
    assert out["action"] == "block" and "負值" in out["message"] and "-19577989" in out["message"]


def test_convert_unit_with_the_minus_sign_is_allowed(plugin):
    assert _convert_after(plugin, NEGATIVE, "-19577989") is None


def test_convert_unit_is_allowed_when_the_figure_also_appears_unsigned(plugin):
    both = '[{"a":-63478.0},{"b":63478.0}]'
    assert _convert_after(plugin, both, "63478") is None


def test_the_sign_check_fails_closed_when_the_router_cannot_load(monkeypatch, tmp_path):
    guard = tmp_path / "src" / "analysis"
    guard.mkdir(parents=True)
    (guard / "answer_guard.py").write_text((ROOT / "src" / "analysis" / "answer_guard.py").read_text(encoding="utf-8"), encoding="utf-8")
    broken = load(monkeypatch, repo=tmp_path)
    out = _convert_after(broken, NEGATIVE, "19577989")
    assert out["action"] == "block" and "無法執行" in out["message"]


def test_the_sign_check_is_only_for_unit_conversion_not_for_calc(plugin):
    plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資買賣超")
    plugin.on_post_tool_call(tool_name="stock_data", result=NEGATIVE, session_id="s1")
    assert calc(plugin, "19577989") is None


def test_a_raw_share_count_relabelled_as_lots_gets_the_wording_note(plugin):
    out = turn(plugin, "鴻海外資最新買賣超幾張", [NEGATIVE], "-19,577,989張")
    assert out and "不能只改單位" in out


FLOW = '[{"date":"2026-10-12","foreign_net":-25348402.0},{"date":"2026-10-13","foreign_net":-19577989.0}]'


def test_conversion_questions_get_the_converted_figures_in_the_injected_context(plugin):
    prefetching(plugin, names={"鴻海": "2317"}, body=FLOW)
    out = plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資最新買賣超是幾張")
    assert "-19577989.0 股 = -19577.989 張" in out["context"]
    assert plugin.on_transform_llm_output(response_text="外資賣超 19577.989 張。", session_id="s1") is None


def test_a_wrong_self_made_conversion_is_still_flagged_after_the_converted_figures_were_given(plugin):
    prefetching(plugin, names={"鴻海": "2317"}, body=FLOW)
    plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資最新買賣超是幾張")
    out = plugin.on_transform_llm_output(response_text="外資買賣超 -195,779.89 張。", session_id="s1")
    assert out and "195779.89" in out.split("找不到出處")[1]


def test_questions_without_conversion_words_get_no_converted_block(plugin):
    prefetching(plugin, names={"鴻海": "2317"}, body=FLOW)
    out = plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資最新買賣超如何")
    assert "程式已精確換算" not in out["context"]


def test_yesterday_in_the_question_gets_yesterdays_row_in_the_injected_context(plugin):
    prefetching(plugin, names={"鴻海": "2317"}, body=FLOW)
    plugin._today = lambda: "2026-10-13"
    out = plugin.on_pre_llm_call(session_id="s1", user_message="鴻海外資昨天買賣超是幾張")
    assert "2026-10-12，昨日）：-25348402.0 股 = -25348.402 張" in out["context"]
    assert "-19577989.0 股 = " not in out["context"]


def test_the_plugin_hands_the_real_date_to_the_router(plugin):
    import datetime

    assert plugin._today() == datetime.date.today().isoformat()
