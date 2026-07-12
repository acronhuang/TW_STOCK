"""
TWSE / TPEX / MOPS OpenAPI 共用工具
===================================
集中政府開放資料 OpenAPI 的共通邏輯——瀏覽器 UA 抓取、民國日期轉換、
數值解析、欄位 fallback——供 sync_revenue / sync_shares / sync_balance_openapi
等同步腳本共用，避免每支各自複製一份（DRY）。

欄名慣例陷阱（呼叫端用 field() 做 fallback）：
  - 財務數值欄位皆中文，但 TWSE 用「總額」、TPEX 用「總計」。
  - 代號欄：TWSE「公司代號」、TPEX「SecuritiesCompanyCode」。
  - 年季欄：多為「年度/季別」，但 TPEX 損益表用英文「Year/Season」。
"""
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 政府 OpenAPI 多會擋預設 UA（302 轉址）→ 一律帶瀏覽器 UA
_HEADERS = {'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/124.0 Safari/537.36')}


def fetch_openapi(url, timeout=60):
    """抓 OpenAPI JSON 陣列。端點失效(HTML/轉址/非200/例外)一律回 []，呼叫端不需 try。"""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, verify=False)
        if r.status_code != 200 or r.text.lstrip().startswith('<'):
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def field(row, *keys):
    """回第一個存在且非空白的欄位值（中英欄名 fallback）；皆無回 None。"""
    for k in keys:
        if k in row and str(row[k]).strip() not in ('', '-'):
            return row[k]
    return None


def to_float(v):
    """字串→float（去千分位）；空值/無效回 None。不做任何單位換算（×1000 由呼叫端決定）。"""
    if v is None:
        return None
    s = str(v).replace(',', '').strip()
    if s in ('', '-', '--', 'N/A'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def roc_to_year(roc):
    """民國年（字串/數字，如 '115'）→ 西元 int（2026）；無效回 None。"""
    s = str(roc).strip()
    return int(s) + 1911 if s.isdigit() else None


def roc_year_month(roc):
    """民國年月 '11505' → '2026-05'；格式不符回 None。"""
    s = str(roc).strip()
    if len(s) == 5 and s.isdigit():
        return f"{int(s[:3]) + 1911}-{s[3:5]}"
    return None
