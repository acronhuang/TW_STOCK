"""給 Hermes Agent 用的唯讀工具：只能對本機分析 API 發出固定白名單內的 GET。"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8888"
MAX_CHARS = 6000
MAX_BYTES = 400_000
DEFAULT_PROTOCOL = "2025-06-18"

# 耗時 18 秒以上的端點（ranking、scan、advisor、hsieh）不開放，避免對話把正式 API 拖慢。
# predict 不開放：它每次都重訓並覆寫 models/<代號>_xgb.pkl，不是唯讀。
STOCK_KINDS = (
    "price", "factors", "valuation", "risk", "peer", "score", "sentiment",
    "anomaly", "institutional", "revenue", "dividend", "financial", "team",
)
MARKET_KINDS = ("macro", "pku", "stocks", "team", "health")

_SYMBOL = re.compile(r"[0-9A-Za-z]{4,8}")
# 產業排名 API 實測接受的 industry_category（2026-10-13 逐一測過）；小模型自由輸入時會產出亂碼字。
INDUSTRIES = (
    "生技醫療業", "電子零組件業", "半導體業", "電機機械", "電腦及週邊設備業", "建材營造", "光電業", "觀光餐旅",
    "通信網路業", "紡織纖維", "鋼鐵工業", "資訊服務業", "綠能環保", "食品工業", "電子通路業", "航運業",
    "文化創意業", "汽車工業", "化學工業", "塑膠工業", "數位雲端", "其他電子業", "電器電纜", "運動休閒",
    "金融業", "油電燃氣業", "橡膠工業", "貿易百貨", "居家生活", "造紙工業", "水泥工業", "玻璃陶瓷",
)

TOOLS = [
    {
        "name": "stock_data",
        "description": "查單一個股的資料。kind：price 股價、factors 因子、valuation 估值、risk 風險、peer 同業比較、"
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
        "description": "查全市場資料。kind：macro 總經與大盤、pku 北大風控、stocks 股票清單、team 全市場團隊研判彙總、health 服務狀態。",
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
]


def default_fetch(url, timeout=30):
    # URL 一律由 build_url 組出且固定指向本機，不接受外部傳入。
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
    return None, f"未知的工具：{name}"


def call_tool(name, args, fetch=default_fetch):
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
