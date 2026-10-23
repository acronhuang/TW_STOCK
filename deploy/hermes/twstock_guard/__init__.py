"""Hermes 外掛：問題進來時先查工具、calc 輸入數字核對出處、回答送出前核對數字（泿用專案的 answer_guard）。"""

import importlib.util
import datetime
import json
import os
import sys
import threading
import time
import urllib.request

_REPO = os.environ.get("TWSTOCK_REPO", "/home/mdsadmin/Stock/tw-stock-analysis")
_GUARD_FILE = os.path.join(_REPO, "src", "analysis", "answer_guard.py")
_ROUTER_FILE = os.path.join(_REPO, "src", "ops", "hermes_router.py")
_TOOLS_FILE = os.path.join(_REPO, "src", "ops", "readonly_tools.py")
_NODES_FILE = os.path.join(_REPO, "src", "moe", "model_nodes.py")
_ROOM_FILE = os.path.join(_REPO, "src", "ops", "hermes_gpu_room.py")
_NAMES_URL = "http://127.0.0.1:8888/api/stocks?limit=3000"
_NAMES_TTL = 6 * 3600
_CHECKED_INPUT = {  # 會產生新數字的工具 → 要核對出處的參數
    "calc": "expression", "mcp__twstock__calc": "expression",
    "convert_unit": "value", "mcp__twstock__convert_unit": "value",
}
_NO_TOOL_NOTE = "⚠️ 本輪沒有查詢任何資料工具，以上內容未經資料驗證，不要當成資料採用。"
_MAX_TURNS = 50

_lock = threading.Lock()
_modules = {}
_names_cache = {"at": 0.0, "map": {}}
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


def _module(path, label):
    if label not in _modules:
        spec = importlib.util.spec_from_file_location(f"twstock_{label}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules[label] = module
    return _modules[label]


def _load_names():
    """名稱→代號，快取 6 小時；取不到就回舊值（可能是空），這時只靠代號比對。"""
    now = time.monotonic()
    if _names_cache["map"] and now - _names_cache["at"] < _NAMES_TTL:
        return _names_cache["map"]
    try:
        with urllib.request.urlopen(_NAMES_URL, timeout=5) as response:  # noqa: S310 - 固定本機網址
            stocks = json.loads(response.read(2_000_000)).get("stocks", [])
    except Exception as error:  # noqa: BLE001 - 名稱表取不到不能擋住對話
        print(f"[twstock-guard] 股票名稱表取不到：{error}", file=sys.stderr)
        return _names_cache["map"]
    _names_cache.update(at=now, map={s["name"]: s["symbol"] for s in stocks if s.get("name") and s.get("symbol")})
    return _names_cache["map"]


def _call_tool(name, args):
    return _module(_TOOLS_FILE, "tools").call_tool(name, args)


def _today():
    return datetime.date.today().isoformat()


def _prefetch(question):
    """回 (結果清單, 附在問題後的上下文)；查不出對象時回 ([], "")。"""
    router = _module(_ROUTER_FILE, "router")
    names = _load_names()
    calls = router.plan(question, names, _module(_TOOLS_FILE, "tools").INDUSTRIES)
    if not calls:
        return [], ""
    results = router.prefetch(calls, _call_tool)
    conversions = router.derive_conversions(results, _module(_TOOLS_FILE, "tools").convert_unit, question, _today())
    return results, router.format_context(
        results, names, router.needs_calculation(question), router.needs_conversion(question), conversions
    )


def _make_room():
    nodes = _module(_NODES_FILE, "nodes")
    return _module(_ROOM_FILE, "room").make_room(
        nodes.HERMES_URL,
        nodes.canonical(nodes.HERMES_MODEL),
        [nodes.canonical(name) for name in nodes.HERMES_EVICT],
    )


def on_pre_llm_call(session_id="", user_message="", **kwargs):
    try:
        unloaded = _make_room()
        if unloaded:
            print(f"[twstock-guard] 為讓 Hermes 完整進 GPU，已卸載：{unloaded}", file=sys.stderr)
    except Exception as error:  # noqa: BLE001 - 卸載失敗只會變慢，不能擋住對話
        print(f"[twstock-guard] 卸載擋路模型失敗：{error}", file=sys.stderr)
    question = _text(user_message)
    texts, context = [], ""
    try:
        results, context = _prefetch(question)
        texts = [context] if results else []
    except Exception as error:  # noqa: BLE001 - 預查失效時照舊讓模型自己查，但要看得見
        print(f"[twstock-guard] 預先查詢失敗：{error}", file=sys.stderr)
        context = ""
    with _lock:
        _turns[session_id] = {"question": question, "tools": texts}
        _last[0] = session_id
        while len(_turns) > _MAX_TURNS:
            _turns.pop(next(iter(_turns)))
    return {"context": context} if context else None


def _lost_sign_block(field, value, context):
    """換算只帶一個數字；它在資料裡是負值卻沒帶負號，換算結果的方向會錯。"""
    if field != "value":
        return None
    text = str(value).strip()
    try:
        negative = _module(_ROUTER_FILE, "router").sign_in_context(text, context) == "neg"
    except Exception as error:  # noqa: BLE001 - 核對失效要擋下，不能放行
        print(f"[twstock-guard] 正負號核對無法執行：{error}", file=sys.stderr)
        return {"action": "block", "message": f"正負號核對無法執行（{type(error).__name__}），不執行換算。"}
    if not negative or text.startswith("-"):
        return None
    return {
        "action": "block",
        "message": f"{text} 在資料中是負值（-{text.replace(',', '')}），請連同負號帶入，否則換算結果的方向會錯。",
    }


def on_pre_tool_call(tool_name="", args=None, session_id="", **kwargs):
    """calc、convert_unit 的輸入數字必須出自本輪問題或工具回傳，否則算出來的結果就成了洗白的自創數字。"""
    field = _CHECKED_INPUT.get(tool_name)
    if field is None:
        return None
    expression = args.get(field, "") if isinstance(args, dict) else ""
    with _lock:
        turn = _turns.get(_current_key(session_id))
    context = "\n".join([turn["question"], *turn["tools"]]) if turn else ""
    try:
        flagged = _unsupported_numbers()(str(expression), context)
    except Exception as error:  # noqa: BLE001 - 核對失效要擋下，不能放行
        print(f"[twstock-guard] calc 核對無法執行：{error}", file=sys.stderr)
        return {"action": "block", "message": f"數字來源核對無法執行（{type(error).__name__}），不執行計算。"}
    if not flagged:
        return _lost_sign_block(field, expression, context)
    return {
        "action": "block",
        "message": f"{tool_name.rsplit('__', 1)[-1]} 的輸入數字 " + "、".join(flagged) + " 不在本輪問題或工具回傳中。請先用工具查出這些數字並逐字帶入，不要自己估計；百分比請寫成 10% 的形式。",
    }


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
    notes = []
    if flagged:
        notes.append("⚠️ 下列數字在本輪工具回傳中找不到出處，請自行核對後再採用：" + "、".join(flagged))
    if turn is not None and not turn["tools"] and _mentions_stock_info(response_text):
        notes.append(_NO_TOOL_NOTE)
    missing = _omitted_holdings(turn["question"] if turn else "", response_text, context)
    if missing:
        notes.append("⚠️ 回答漏列了持倉：" + "、".join(missing) + "，請以查詢結果為準。")
    no_shares = _omitted_shares(turn["question"] if turn else "", response_text, context)
    if no_shares:
        notes.append("⚠️ 下列持倉的回答沒有寫出股數：" + "、".join(no_shares) + "，請以查詢結果為準。")
    issues = _language_issues(response_text, context)
    if issues:
        notes.append("⚠️ 用詞與單位提醒：" + "；".join(issues) + "。以資料原欄位與單位為準。")
    return response_text + "\n\n" + "\n".join(notes) if notes else None


def _mentions_stock_info(text):
    try:
        return _module(_ROUTER_FILE, "router").mentions_stock_info(text)
    except Exception as error:  # noqa: BLE001 - 判斷失效時寧可多給警語
        print(f"[twstock-guard] 股票資訊判斷無法執行：{error}", file=sys.stderr)
        return True


def _omitted_holdings(question, text, context):
    try:
        return _module(_ROUTER_FILE, "router").omitted_holdings(question, text, context)
    except Exception as error:  # noqa: BLE001 - 漏列檢查失效不能擋住回答
        print(f"[twstock-guard] 漏列檢查無法執行：{error}", file=sys.stderr)
        return []


def _omitted_shares(question, text, context):
    try:
        return _module(_ROUTER_FILE, "router").omitted_shares(question, text, context)
    except Exception as error:  # noqa: BLE001 - 漏列檢查失效不能擋住回答
        print(f"[twstock-guard] 股數檢查無法執行：{error}", file=sys.stderr)
        return []


def _language_issues(text, context=""):
    try:
        return _module(_ROUTER_FILE, "router").language_issues(text, context)
    except Exception as error:  # noqa: BLE001 - 用詞檢查失效不能擋住回答
        print(f"[twstock-guard] 用詞檢查無法執行：{error}", file=sys.stderr)
        return []


def register(ctx):
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
