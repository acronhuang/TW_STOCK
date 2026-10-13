"""查 FinMind 伺服器端已用量，供每小時下載記進日誌。"""

import requests

URL = "https://api.web.finmindtrade.com/v2/user_info"


def fetch_usage(token, get=requests.get, timeout=10):
    """回傳 (已用, 上限)；任何失敗或欄位不合法一律回 None，不回 0。"""
    if not token:
        return None
    try:
        response = get(URL, params={"token": token}, timeout=timeout)
        if response.status_code != 200:
            return None
        body = response.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(body, dict) or body.get("status") != 200:
        return None
    used, limit = body.get("user_count"), body.get("api_request_limit")
    for value in (used, limit):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
    if used < 0 or limit <= 0:
        return None
    return used, limit


def describe(usage):
    if usage is None:
        return "伺服器端用量無資料"
    used, limit = usage
    return f"伺服器端用量 {used}/{limit}"
