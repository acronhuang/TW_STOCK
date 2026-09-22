"""供互動頁面使用的外部網頁補充搜尋。"""
from __future__ import annotations

import re

import requests
from urllib.parse import urlparse

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
WEB_SUPPLEMENT_MIN_SIMILARITY = 0.60
# 防資源耗用/XSS 面：外部 RSS 回應與欄位長度上限。
MAX_RESPONSE_BYTES = 1_000_000
MAX_TITLE_LEN = 300
NEWS_REGIONS = {
    "taiwan_zh": {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant", "label": "繁中解讀"},
    "international_en": {"hl": "en-US", "gl": "US", "ceid": "US:en", "label": "國際英文原始新聞"},
    "japan_ja": {"hl": "ja", "gl": "JP", "ceid": "JP:ja", "label": "日本新聞"},
    "china_zh": {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans", "label": "中國新聞（簡中）"},
    "hong_kong_zh": {"hl": "zh-HK", "gl": "HK", "ceid": "HK:zh-Hant", "label": "香港新聞（繁中）"},
}
INTERNATIONAL_SOURCE_QUERY = "(site:reuters.com OR site:bloomberg.com OR site:cnbc.com OR site:ft.com)"


def _rss_value(item: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def google_news_search(
        query: str, max_items: int = 5, timeout: int = 6, region: str = "taiwan_zh") -> list[dict[str, str]]:
    """回傳 Google News RSS 結果。外部服務失敗時回空，不影響本機檢索。"""
    if not query:
        return []
    config = NEWS_REGIONS.get(region, NEWS_REGIONS["taiwan_zh"])
    search_query = f"{query} {INTERNATIONAL_SOURCE_QUERY}" if region == "international_en" else query
    try:
        response = requests.get(
            GOOGLE_NEWS_RSS,
            params={"q": search_query, "hl": config["hl"], "gl": config["gl"], "ceid": config["ceid"]},
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux) Chrome/120"},
        )
        response.raise_for_status()
        body = response.text[:MAX_RESPONSE_BYTES]  # 上限解析量，降低 ReDoS/資源耗用風險
        results = []
        seen_urls = set()
        for item in re.findall(r"<item>(.*?)</item>", body, re.DOTALL)[:max_items]:
            title = _rss_value(item, "title")
            url = _rss_value(item, "link")
            if title and url and url not in seen_urls:
                seen_urls.add(url)
                results.append({
                    "title": title[:MAX_TITLE_LEN],
                    "url": url[:MAX_TITLE_LEN],
                    "published_at": _rss_value(item, "pubDate"),
                    "source": f"Google News RSS · {config['label']}",
                })
        return results
    except requests.RequestException:
        return []


NEWS_MODE_REGIONS = {
    "繁中解讀": ("taiwan_zh",),
    "國際英文原始新聞": ("international_en",),
    "日本新聞": ("japan_ja",),
    "中國新聞（簡中）": ("china_zh",),
    "香港新聞（繁中）": ("hong_kong_zh",),
    "綜合：繁中＋英文原始": ("taiwan_zh", "international_en"),
    "綜合：所有來源": ("taiwan_zh", "international_en", "japan_ja", "china_zh", "hong_kong_zh"),
}


def search_news_by_mode(query: str, mode: str, max_items: int = 5) -> dict[str, list[dict[str, str]]]:
    """依使用者選擇的地區模式查新聞，綜合模式保留各來源群組。"""
    regions = NEWS_MODE_REGIONS.get(mode, NEWS_MODE_REGIONS["繁中解讀"])
    return {
        NEWS_REGIONS[region]["label"]: google_news_search(query, max_items=max_items, region=region)
        for region in regions
    }


def needs_web_supplement(rows: list[dict]) -> bool:
    """本機語料沒有命中或最高語意相似度不足時，允許顯示外部補充。"""
    return not rows or float(rows[0].get("vec_sim", 0.0)) < WEB_SUPPLEMENT_MIN_SIMILARITY


# ── 展示安全：外部 RSS 標題/連結顯示前必須消毒（XSS / CWE-79）。
_MD_ESCAPE = str.maketrans({c: "\\" + c for c in "[]()*_`~<>"})


def sanitize_markdown_text(text: str) -> str:
    """轉義 markdown 特殊字元並拉直換行，避免外部標題注入連結/格式/HTML。"""
    return (text or "").translate(_MD_ESCAPE).replace("\n", " ").replace("\r", " ")


def safe_external_url(url: str) -> str:
    """僅允許 http(s) 連結；javascript:/data: 等危險 scheme 回空字串。"""
    try:
        scheme = urlparse(url or "").scheme.lower()
    except ValueError:
        return ""
    return url if scheme in ("http", "https") else ""