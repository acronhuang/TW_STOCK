"""Hermes 外掛：回答送出前，核對數字是否出自本輪的問題或工具回傳（沿用專案的 answer_guard）。"""

import importlib.util
import os
import sys
import threading

_REPO = os.environ.get("TWSTOCK_REPO", "/home/mdsadmin/Stock/tw-stock-analysis")
_GUARD_FILE = os.path.join(_REPO, "src", "analysis", "answer_guard.py")
_MAX_TURNS = 50

_lock = threading.Lock()
_turns = {}
_last = [None]
_guard = [None]


def _unsupported_numbers():
    if _guard[0] is None:
        spec = importlib.util.spec_from_file_location("twstock_answer_guard", _GUARD_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _guard[0] = module.unsupported_numbers
    return _guard[0]


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in value)
    return str(value or "")


def _current_key(session_id):
    return session_id if session_id in _turns else _last[0]


def on_pre_llm_call(session_id="", user_message="", **kwargs):
    with _lock:
        _turns[session_id] = {"question": _text(user_message), "tools": []}
        _last[0] = session_id
        while len(_turns) > _MAX_TURNS:
            _turns.pop(next(iter(_turns)))
    return None


def on_post_tool_call(tool_name="", result="", session_id="", **kwargs):
    with _lock:
        key = _current_key(session_id)
        if key in _turns:
            _turns[key]["tools"].append(_text(result))
    return None


def on_transform_llm_output(response_text="", session_id="", **kwargs):
    if not response_text:
        return None
    with _lock:
        key = _current_key(session_id)
        turn = _turns.pop(key, None)
        if _last[0] == key:
            _last[0] = None
    context = "\n".join([turn["question"], *turn["tools"]]) if turn else ""
    try:
        flagged = _unsupported_numbers()(response_text, context)
    except Exception as error:  # noqa: BLE001 - 守門失效要看得見，不能靜默放行
        print(f"[twstock-guard] 數字核對無法執行：{error}", file=sys.stderr)
        return response_text + f"\n\n⚠️ 數字核對未執行（{type(error).__name__}），回答中的數字請自行核對。"
    if not flagged:
        return None
    return response_text + "\n\n⚠️ 下列數字在本輪工具回傳中找不到出處，請自行核對後再採用：" + "、".join(flagged)


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
