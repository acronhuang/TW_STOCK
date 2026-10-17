"""給 Hermes Agent 用的唯讀工具：只能對本機分析 API 發出固定白名單內的 GET。"""

import ast
import json
import operator
from decimal import Decimal, InvalidOperation
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8888"
MAX_CHARS = 6000
MAX_BYTES = 400_000
DEFAULT_PROTOCOL = "2025-06-18"

# 耗時約 18~24 秒的端點（ranking、scan、advisor、hsieh）依使用者 2026-10-17 的決定開放，逾時放寬到 HEAVY_TIMEOUT。
# predict 不開放：它每次都重訓並覆寫 models/<代號>_xgb.pkl，不是唯讀。
STOCK_KINDS = (
    "price", "factors", "valuation", "risk", "peer", "score", "sentiment",
    "anomaly", "institutional", "revenue", "dividend", "financial", "team", "hsieh",
)
MARKET_KINDS = ("macro", "pku", "stocks", "team", "health", "ranking", "scan", "advisor", "hsieh")
PORTFOLIO_KINDS = ("positions", "lots", "trades")
HEAVY_TIMEOUT = 120
HEAVY_PREFIXES = ("/api/ranking", "/api/scan", "/api/advisor", "/api/hsieh")

_SYMBOL = re.compile(r"[0-9A-Za-z]{4,8}")
# 產業排名 API 實測接受的 industry_category（2026-10-13 逐一測過）；小模型自由輸入時會產出亂碼字。
INDUSTRIES = (
    "生技醫療業", "電子零組件業", "半導體業", "電機機械", "電腦及週邊設備業", "建材營造", "光電業", "觀光餐旅",
    "通信網路業", "紡織纖維", "鋼鐵工業", "資訊服務業", "綠能環保", "食品工業", "電子通路業", "航運業",
    "文化創意業", "汽車工業", "化學工業", "塑膠工業", "數位雲端", "其他電子業", "電器電纜", "運動休閒",
    "金融業", "油電燃氣業", "橡膠工業", "貿易百貨", "居家生活", "造紙工業", "水泥工業", "玻璃陶瓷",
)

# 金額換成元的倍數、股數換成股的倍數（1 張＝1000 股）；表內的單位就是 convert_unit 接受的單位。
MONEY_UNITS = {"元": 1, "千元": 1000, "萬元": 10000, "百萬元": 1000000, "億元": 100000000}
SHARE_UNITS = {"股": 1, "張": 1000}
MAX_VALUE_CHARS = 20
_NUMBER_TEXT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

TOOLS = [
    {
        "name": "stock_data",
        "description": "查單一個股的資料（hsieh 是謝富旭研究分析，要 20 秒以上）。kind：price 股價、factors 因子、valuation 估值、risk 風險、peer 同業比較、"
        "score 評分、sentiment 情緒、anomaly 異常、institutional 法人、revenue 月營收、"
        "dividend 股利、financial 財報、team AI 團隊研判。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(STOCK_KINDS)},
                "symbol": {"type": "string", "description": "股票代號，例如 2330"},
            },
            "required": ["kind", "symbol"],
        },
    },
    {
        "name": "market_data",
        "description": "查全市場資料（ranking 綜合選股排行、scan 全市場掃描加風險篩選、advisor 策略交易建議、hsieh 存股選股，這四項要 20 秒以上）。kind：macro 總經與大盤、pku 北大風控、stocks 股票清單、team 全市場團隊研判彙總、health 服務狀態。",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(MARKET_KINDS)}},
            "required": ["kind"],
        },
    },
    {
        "name": "industry_data",
        "description": "查某個產業的個股排名，industry 必須是清單內的產業名稱，例如 半導體業。",
        "inputSchema": {
            "type": "object",
            "properties": {"industry": {"type": "string", "enum": list(INDUSTRIES)}},
            "required": ["industry"],
        },
    },
    {
        "name": "calc",
        "description": "四則運算。expression 只能含數字、+ - * /、括號與百分號，例如 2540*(1+10%) - 942.5。"
        "數字必須逐字取自工具回傳或使用者問題，不得自己估計；回答只能引用本工具回傳的結果。",
        "inputSchema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "算式，例如 2540*(1+10%) - 942.5"}},
            "required": ["expression"],
        },
    },
    {
        "name": "convert_unit",
        "description": "單位換算（精確）：金額在 元、千元、萬元、百萬元、億元 之間，股數在 股、張 之間。"
        "value 必須逐字取自工具回傳或使用者問題；回答只能引用本工具回傳的結果，不要自己換算。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "description": "要換算的數字，例如 511857399"},
                "from_unit": {"type": "string", "enum": list(MONEY_UNITS) + list(SHARE_UNITS)},
                "to_unit": {"type": "string", "enum": list(MONEY_UNITS) + list(SHARE_UNITS)},
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
    {
        "name": "portfolio_data",
        "description": "查使用者的持倉（唯讀）。kind：positions 目前持倉（股數、均價、總成本）、lots 買進批次、trades 交易紀錄。"
        "股數單位是股，價格與成本單位是元；回答只能引用本工具回傳的數字。",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(PORTFOLIO_KINDS)}},
            "required": ["kind"],
        },
    },
]

MAX_EXPRESSION = 120
_ALLOWED = re.compile(r"[0-9+\-*/().%\s]+")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError("算式只能含數字、+ - * /、括號與百分號")


def calculate(expression):
    """回 (文字, 是否錯誤)。百分號先轉成除以 100，再以 AST 白名單運算，不使用 eval。"""
    if not isinstance(expression, str) or not expression.strip():
        return "expression 必須是非空字串", True
    if len(expression) > MAX_EXPRESSION:
        return f"expression 超過 {MAX_EXPRESSION} 字", True
    if not _ALLOWED.fullmatch(expression):
        return "算式只能含數字、+ - * /、括號與百分號", True
    try:
        tree = ast.parse(_PERCENT.sub(r"(\1/100)", expression.strip()), mode="eval")
        value = _eval(tree)
    except ZeroDivisionError:
        return "除數不能為 0", True
    except (SyntaxError, ValueError, RecursionError):
        return "算式只能含數字、+ - * /、括號與百分號", True
    if abs(value) >= 1e15:
        return "結果過大", True
    shown = f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{expression.strip()} = {'0' if shown in ('', '-0') else shown}", False


def convert_unit(value, from_unit, to_unit):
    """回 (文字, 是否錯誤)。以 Decimal 精確換算，只在同一類單位間換（金額或股數）。"""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return "value 必須是數字", True
    text = str(value).strip()
    if len(text) > MAX_VALUE_CHARS or not _NUMBER_TEXT.fullmatch(text):
        return "value 必須是數字（可含千分位逗號與小數點，最多 20 字）", True
    if not isinstance(from_unit, str) or not isinstance(to_unit, str):
        return "from_unit、to_unit 必須是單位名稱", True
    for table in (MONEY_UNITS, SHARE_UNITS):
        if from_unit in table and to_unit in table:
            break
    else:
        return "單位只能在金額（元、千元、萬元、百萬元、億元）或股數（股、張）內換算", True
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return "value 必須是數字", True
    shown = format((number * table[from_unit] / table[to_unit]).normalize(), "f")
    return f"{text} {from_unit} = {shown} {to_unit}", False


def default_fetch(url, timeout=None):
    # URL 一律由 build_url 組出且固定指向本機，不接受外部傳入。
    if timeout is None:
        timeout = HEAVY_TIMEOUT if url.startswith(tuple(BASE + p for p in HEAVY_PREFIXES)) else 30
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return response.status, response.read(MAX_BYTES).decode("utf-8", "replace")


def build_url(name, args):
    """回傳 (url, 錯誤訊息)；參數不合白名單時 url 為 None。"""
    if not isinstance(args, dict):
        return None, "參數必須是物件"
    if name == "stock_data":
        kind, symbol = args.get("kind"), args.get("symbol")
        if kind not in STOCK_KINDS:
            return None, f"kind 不在允許清單：{', '.join(STOCK_KINDS)}"
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            return None, "symbol 必須是 4 到 8 碼的英數字股票代號"
        if kind == "hsieh":
            return f"{BASE}/api/hsieh/research/{symbol}", None
        return f"{BASE}/api/{kind}/{symbol}", None
    if name == "market_data":
        kind = args.get("kind")
        if kind not in MARKET_KINDS:
            return None, f"kind 不在允許清單：{', '.join(MARKET_KINDS)}"
        return f"{BASE}/api/{kind}", None
    if name == "industry_data":
        industry = args.get("industry")
        if industry not in INDUSTRIES:
            return None, f"industry 不在允許清單：{', '.join(INDUSTRIES)}"
        return f"{BASE}/api/industry/{urllib.parse.quote(industry)}", None
    if name == "portfolio_data":
        kind = args.get("kind")
        if kind not in PORTFOLIO_KINDS:
            return None, f"kind 不在允許清單：{', '.join(PORTFOLIO_KINDS)}"
        return f"{BASE}/api/portfolio/{kind}", None
    return None, f"未知的工具：{name}"


def call_tool(name, args, fetch=default_fetch):
    if name == "calc":
        return calculate(args.get("expression") if isinstance(args, dict) else None)
    if name == "convert_unit":
        given = args if isinstance(args, dict) else {}
        return convert_unit(given.get("value"), given.get("from_unit"), given.get("to_unit"))
    url, error = build_url(name, args)
    if url is None:
        return error, True
    try:
        status, body = fetch(url)
    except urllib.error.HTTPError as exc:
        return f"API 回應 HTTP {exc.code}", True
    except (urllib.error.URLError, OSError) as exc:
        return f"API 無法連線：{exc}", True
    if status != 200:
        return f"API 回應 HTTP {status}", True
    if len(body) > MAX_CHARS:
        return f"{body[:MAX_CHARS]}\n[已截斷，原長 {len(body)} 字]", False
    return body, False


def handle_message(msg, fetch=default_fetch):
    """處理一則 JSON-RPC 訊息；通知（沒有 id）不回覆。"""
    if not isinstance(msg, dict) or "id" not in msg:
        return None
    mid, method = msg["id"], msg.get("method")
    params = msg.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "twstock-readonly", "version": "1"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        text, is_error = call_tool(params.get("name"), params.get("arguments") or {}, fetch)
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(lines, write, fetch=default_fetch):
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        reply = handle_message(msg, fetch)
        if reply is not None:
            write(reply)
