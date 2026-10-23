"""TDD: Hermes 的唯讀工具只能對本機 API 發出白名單內的 GET，參數不合法時不發出請求。"""

import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from src.ops import readonly_tools as ro

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent


class Recorder:
    def __init__(self, status=200, body='{"ok": true}', error=None):
        self.urls, self.status, self.body, self.error = [], status, body, error

    def __call__(self, url, timeout=30):
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.status, self.body


def test_exactly_these_tools_with_the_allowed_kinds():
    tools = {t["name"]: t for t in ro.TOOLS}
    assert set(tools) == {"stock_data", "market_data", "industry_data", "calc", "convert_unit", "portfolio_data", "plan_review"}
    assert tools["portfolio_data"]["inputSchema"]["properties"]["kind"]["enum"] == list(ro.PORTFOLIO_KINDS)
    assert tools["stock_data"]["inputSchema"]["properties"]["kind"]["enum"] == list(ro.STOCK_KINDS)
    assert tools["market_data"]["inputSchema"]["properties"]["kind"]["enum"] == list(ro.MARKET_KINDS)


def test_slow_endpoints_are_exposed_by_the_users_decision():
    assert {"ranking", "scan", "advisor", "hsieh"} <= set(ro.MARKET_KINDS) and "hsieh" in ro.STOCK_KINDS


def test_endpoints_that_write_files_are_not_exposed():
    # predict 會重訓並覆寫 models/<代號>_xgb.pkl
    assert "predict" not in ro.STOCK_KINDS and "predict" not in ro.MARKET_KINDS


def test_stock_and_market_calls_hit_the_expected_urls():
    fetch = Recorder()
    ro.call_tool("stock_data", {"kind": "valuation", "symbol": "2330"}, fetch)
    ro.call_tool("market_data", {"kind": "macro"}, fetch)
    ro.call_tool("industry_data", {"industry": "半導體業"}, fetch)
    assert fetch.urls == [
        "http://127.0.0.1:8888/api/valuation/2330",
        "http://127.0.0.1:8888/api/macro",
        "http://127.0.0.1:8888/api/industry/%E5%8D%8A%E5%B0%8E%E9%AB%94%E6%A5%AD",
    ]


@pytest.mark.parametrize("kind", ["ranking", "scan", "../admin", "price/../x", "", None, 5])
def test_unknown_stock_kind_is_rejected_without_a_request(kind):
    fetch = Recorder()
    text, is_error = ro.call_tool("stock_data", {"kind": kind, "symbol": "2330"}, fetch)
    assert is_error and fetch.urls == []


@pytest.mark.parametrize("symbol", ["", "23", "2330/../x", "2330?x=1", "2330 ", "../..", "233%2F", None, 2330, "123456789"])
def test_bad_symbol_is_rejected_without_a_request(symbol):
    fetch = Recorder()
    _, is_error = ro.call_tool("stock_data", {"kind": "price", "symbol": symbol}, fetch)
    assert is_error and fetch.urls == []


@pytest.mark.parametrize(
    "industry", ["", "a/b", "半導體?x=1", "x" * 21, "..", None, "半導體\n", "中学米演览分", "電子工業", "金融保險", ["半導體業"]]
)
def test_bad_industry_is_rejected_without_a_request(industry):
    fetch = Recorder()
    _, is_error = ro.call_tool("industry_data", {"industry": industry}, fetch)
    assert is_error and fetch.urls == []


def test_industry_schema_lists_exactly_the_accepted_names():
    schema = {t["name"]: t for t in ro.TOOLS}["industry_data"]["inputSchema"]
    assert schema["properties"]["industry"]["enum"] == list(ro.INDUSTRIES)
    assert len(set(ro.INDUSTRIES)) == len(ro.INDUSTRIES) and "其他" not in ro.INDUSTRIES


def test_every_listed_industry_builds_a_quoted_local_url():
    fetch = Recorder()
    for name in ro.INDUSTRIES:
        ro.call_tool("industry_data", {"industry": name}, fetch)
    assert len(fetch.urls) == len(ro.INDUSTRIES)
    assert all(u.startswith("http://127.0.0.1:8888/api/industry/%") and u.isascii() for u in fetch.urls)


def test_unknown_tool_and_non_object_arguments_are_errors():
    fetch = Recorder()
    assert ro.call_tool("delete_all", {}, fetch)[1] and ro.call_tool("stock_data", "2330", fetch)[1]
    assert fetch.urls == []


def test_every_allowed_call_stays_under_the_local_api_prefix():
    fetch = Recorder()
    for kind in ro.STOCK_KINDS:
        ro.call_tool("stock_data", {"kind": kind, "symbol": "2330"}, fetch)
    for kind in ro.MARKET_KINDS:
        ro.call_tool("market_data", {"kind": kind}, fetch)
    for kind in ro.PORTFOLIO_KINDS:
        ro.call_tool("portfolio_data", {"kind": kind}, fetch)
    assert len(fetch.urls) == len(ro.STOCK_KINDS) + len(ro.MARKET_KINDS) + len(ro.PORTFOLIO_KINDS)
    assert all(u.startswith("http://127.0.0.1:8888/api/") for u in fetch.urls)


def test_long_body_is_truncated_and_says_so():
    text, is_error = ro.call_tool("market_data", {"kind": "macro"}, Recorder(body="x" * 20000))
    assert not is_error and text.startswith("x" * ro.MAX_CHARS) and "已截斷，原長 20000 字" in text
    assert len(text) < ro.MAX_CHARS + 60


def test_short_body_is_returned_whole():
    assert ro.call_tool("market_data", {"kind": "macro"}, Recorder(body="abc")) == ("abc", False)


@pytest.mark.parametrize(
    "fetch, expected",
    [
        (Recorder(error=urllib.error.HTTPError("u", 404, "nf", {}, None)), "HTTP 404"),
        (Recorder(error=urllib.error.URLError("refused")), "無法連線"),
        (Recorder(error=TimeoutError("slow")), "無法連線"),
        (Recorder(status=500, body="boom"), "HTTP 500"),
    ],
    ids=["http404", "refused", "timeout", "status500"],
)
def test_api_failures_become_error_results_not_exceptions(fetch, expected):
    text, is_error = ro.call_tool("stock_data", {"kind": "price", "symbol": "2330"}, fetch)
    assert is_error and text.startswith("API ") and expected in text


def test_initialize_echoes_the_client_protocol_and_declares_tools():
    reply = ro.handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
    assert reply["id"] == 0 and reply["result"]["protocolVersion"] == "2025-03-26"
    assert "tools" in reply["result"]["capabilities"]


def test_notifications_get_no_reply_but_id_zero_does():
    assert ro.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert ro.handle_message({"jsonrpc": "2.0", "id": 0, "method": "ping"})["result"] == {}


def test_unknown_method_is_a_json_rpc_error():
    reply = ro.handle_message({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
    assert reply["error"]["code"] == -32601 and reply["id"] == 7


def test_tools_call_wraps_the_text_and_error_flag():
    ok = ro.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "market_data", "arguments": {"kind": "health"}}},
        Recorder(body="up"),
    )
    assert ok["result"] == {"content": [{"type": "text", "text": "up"}], "isError": False}
    bad = ro.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "market_data", "arguments": {"kind": "predict"}}},
        Recorder(),
    )
    assert bad["result"]["isError"] is True


def test_serve_survives_garbage_and_blank_lines():
    out = []
    ro.serve(io.StringIO("\nnot json\n" + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}) + "\n"), out.append)
    assert out[0]["error"]["code"] == -32700 and out[1]["id"] == 3


def test_script_speaks_mcp_over_stdio_without_network():
    requests = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]) + "\n"
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "hermes_readonly_mcp.py")],
        input=requests, capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=30,
    )
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    assert done.returncode == 0 and [r["id"] for r in replies] == [1, 2]
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["stock_data", "market_data", "industry_data", "calc", "convert_unit", "portfolio_data", "plan_review"]


@pytest.mark.parametrize(
    "expression, shown",
    [
        ("2540*(1+10%)", "2540*(1+10%) = 2794"),
        ("2540*1.1-942.5", "2540*1.1-942.5 = 1851.5"),
        ("-(3+4)*2", "-(3+4)*2 = -14"),
        ("10/4", "10/4 = 2.5"),
        ("1/3", "1/3 = 0.333333"),
        ("1234567.89+1", "1234567.89+1 = 1234568.89"),
        ("0.1+0.2-0.3", "0.1+0.2-0.3 = 0"),
        ("0.3-0.1-0.2", "0.3-0.1-0.2 = 0"),
    ],
)
def test_calc_does_plain_arithmetic_and_shows_the_expression(expression, shown):
    assert ro.calculate(expression) == (shown, False)


@pytest.mark.parametrize(
    "expression",
    ["__import__('os').system('x')", "2**8", "abs(-1)", "a+1", "1+", "", "   ", "[1]", "1 if 1 else 2", "1e3", "2540 // 3", "7 % 3", None, 5],
)
def test_calc_rejects_anything_but_numbers_and_four_operations(expression):
    text, is_error = ro.calculate(expression)
    assert is_error is True and "=" not in text


def test_calc_division_by_zero_and_huge_results_are_errors():
    assert ro.calculate("1/0") == ("除數不能為 0", True)
    assert ro.calculate("99999999*99999999*99999999")[1] is True
    assert ro.calculate("1+" * 100 + "1")[1] is True


def test_calc_is_reachable_through_call_tool_and_the_mcp_message():
    assert ro.call_tool("calc", {"expression": "2*3"}) == ("2*3 = 6", False)
    assert ro.call_tool("calc", None)[1] is True
    reply = ro.handle_message(
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "calc", "arguments": {"expression": "1+1"}}},
        Recorder(),
    )
    assert reply["result"]["content"][0]["text"] == "1+1 = 2" and reply["result"]["isError"] is False


@pytest.mark.parametrize(
    "value, source, target, shown",
    [
        ("511857399", "千元", "億元", "511857399 千元 = 5118.57399 億元"),
        ("511,857,399", "千元", "億元", "511,857,399 千元 = 5118.57399 億元"),
        ("765000", "股", "張", "765000 股 = 765 張"),
        ("-19577989", "股", "張", "-19577989 股 = -19577.989 張"),
        ("1.5", "億元", "元", "1.5 億元 = 150000000 元"),
        ("1", "萬元", "元", "1 萬元 = 10000 元"),
        ("100", "百萬元", "億元", "100 百萬元 = 1 億元"),
        ("0", "元", "億元", "0 元 = 0 億元"),
        (100, "百萬元", "億元", "100 百萬元 = 1 億元"),
        ("12", "張", "股", "12 張 = 12000 股"),
    ],
)
def test_convert_unit_is_exact_for_every_unit(value, source, target, shown):
    assert ro.convert_unit(value, source, target) == (shown, False)


@pytest.mark.parametrize(
    "value, source, target",
    [
        ("abc", "千元", "億元"),
        ("", "千元", "億元"),
        ("1e9", "千元", "億元"),
        ("1" * 21, "千元", "億元"),
        ("1", "元", "股"),
        ("1", "張", "億元"),
        ("1", "元", "美元"),
        ("1", ["元"], "億元"),
        (True, "元", "億元"),
        (None, "元", "億元"),
    ],
)
def test_convert_unit_refuses_bad_input_and_cross_family_conversion(value, source, target):
    text, is_error = ro.convert_unit(value, source, target)
    assert is_error is True and text


def test_convert_unit_is_reachable_through_call_tool_and_the_mcp_message():
    args = {"value": "511857399", "from_unit": "千元", "to_unit": "億元"}
    assert ro.call_tool("convert_unit", args) == ("511857399 千元 = 5118.57399 億元", False)
    assert ro.call_tool("convert_unit", None)[1] is True
    reply = ro.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "convert_unit", "arguments": args}})
    assert reply["result"]["isError"] is False and "5118.57399" in reply["result"]["content"][0]["text"]


def test_convert_unit_schema_offers_exactly_the_units_it_accepts():
    schema = {t["name"]: t for t in ro.TOOLS}["convert_unit"]["inputSchema"]["properties"]
    assert set(schema["from_unit"]["enum"]) == set(schema["to_unit"]["enum"]) == set(ro.MONEY_UNITS) | set(ro.SHARE_UNITS)


def test_heavy_endpoints_build_the_right_urls():
    fetch = Recorder()
    for kind in ("ranking", "scan", "advisor", "hsieh"):
        ro.call_tool("market_data", {"kind": kind}, fetch)
    ro.call_tool("stock_data", {"kind": "hsieh", "symbol": "2330"}, fetch)
    base = "http://127.0.0.1:8888/api/"
    assert fetch.urls == [base + "ranking", base + "scan", base + "advisor", base + "hsieh", base + "hsieh/research/2330"]


class _Response:
    status = 200

    def read(self, size):
        return b"[]"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_heavy_endpoints_get_a_longer_timeout_and_the_rest_keep_thirty_seconds(monkeypatch):
    seen = []
    monkeypatch.setattr(ro.urllib.request, "urlopen", lambda url, timeout: seen.append((url, timeout)) or _Response())
    for path in ("/api/scan", "/api/hsieh/research/2330", "/api/ranking", "/api/advisor", "/api/price/2330"):
        ro.default_fetch("http://127.0.0.1:8888" + path)
    assert [timeout for _, timeout in seen] == [ro.HEAVY_TIMEOUT] * 4 + [30]


def test_an_explicit_timeout_is_respected(monkeypatch):
    seen = []
    monkeypatch.setattr(ro.urllib.request, "urlopen", lambda url, timeout: seen.append(timeout) or _Response())
    ro.default_fetch("http://127.0.0.1:8888/api/scan", timeout=5)
    assert seen == [5]


@pytest.mark.parametrize("kind", ["positions", "lots", "trades"])
def test_portfolio_calls_hit_the_local_read_only_endpoint(kind):
    fetch = Recorder()
    ro.call_tool("portfolio_data", {"kind": kind}, fetch)
    assert fetch.urls == [f"http://127.0.0.1:8888/api/portfolio/{kind}"]


@pytest.mark.parametrize("kind", ["../admin", "position", "", None, 5, "positions/x", "trades?limit=1"])
def test_bad_portfolio_kind_is_rejected_without_a_request(kind):
    fetch = Recorder()
    text, is_error = ro.call_tool("portfolio_data", {"kind": kind}, fetch)
    assert is_error and "允許清單" in text and fetch.urls == []


class Routes:
    """依網址回傳固定內容的假取數函式。"""

    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def __call__(self, url, timeout=30):
        self.urls.append(url)
        value = self.routes.get(url.replace(ro.BASE, ""))
        if isinstance(value, Exception):
            raise value
        return (200, json.dumps(value, ensure_ascii=False)) if value is not None else (404, "")


PLAN_ROUTES = {
    "/api/risk/2330": {"current_price": 100.0, "position_sizing": {"max_position_pct": 3.9}, "atr": {"n": 2.0, "stop_2n": 96.0}},
    "/api/factors/2330": {"close": 100.0, "ma_bias_20": 1.0, "rsi_14": 50.0, "return_1m": 2.0},
    "/api/portfolio/positions": [],
}


def test_plan_review_reads_three_get_endpoints_and_returns_the_rendered_review():
    fetch = Routes(PLAN_ROUTES)
    text, is_error = ro.call_tool("plan_review", {"symbol": "2330", "action": "買進", "entry": 100, "stop": 96, "lots": 1, "capital": 1000000}, fetch)

    assert not is_error and text.startswith("計畫審查") and "結論：" in text and "1. 止損：通過" in text
    assert sorted(url.replace(ro.BASE, "") for url in fetch.urls) == sorted(PLAN_ROUTES)


def test_plan_review_marks_unavailable_sources_as_missing_data_instead_of_guessing():
    fetch = Routes({"/api/risk/2330": None, "/api/factors/2330": urllib.error.URLError("down"), "/api/portfolio/positions": None})
    text, is_error = ro.call_tool("plan_review", {"symbol": "2330", "action": "買進", "stop": 96, "lots": 1, "capital": 1000000}, fetch)

    assert not is_error and "資料不足" in text and "追高：資料不足" in text and "攤平：資料不足" in text


def test_plan_review_rejects_bad_arguments_without_any_request():
    fetch = Routes(PLAN_ROUTES)
    for args in ({"symbol": "../x", "action": "買進"}, {"symbol": "2330", "action": "下單"}, {"symbol": "2330", "action": "買進", "entry": -1}, None):
        text, is_error = ro.call_tool("plan_review", args, fetch)
        assert is_error and text
    assert fetch.urls == []


def test_plan_review_only_issues_get_requests_to_the_allowed_endpoints():
    fetch = Routes(PLAN_ROUTES)
    ro.call_tool("plan_review", {"symbol": "2330", "action": "賣出", "lots": 1}, fetch)
    assert all(url.startswith(ro.BASE + "/api/") for url in fetch.urls)
    assert not any("predict" in url or "scan" in url for url in fetch.urls)
