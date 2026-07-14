"""
新聞佐證 —— 給團隊分析的「基本面事件」佐證
==========================================
量價/籌碼看不到「發生什麼事」；本模組補上新聞事件佐證，餵給分析師研判：
  1. major_news：TWSE 官方公司重大訊息（已入庫，可靠、免費、無外部依賴）
  2. Google News RSS：媒體新聞標題（免費、無需 key；best-effort，失敗不影響分析）
  3. media_news：全市場媒體新聞「預抓快取」（scripts/media_news_sync.py 產出）

新聞來源分流（避免全市場 2000 檔逐一即時外抓被 Google 限流）：
  - 小批 / 手動（NEWS_GOOGLE≠0）：即時抓 Google 取最新，抓不到退回預抓快取。
  - 全市場批次（NEWS_GOOGLE=0）：只讀 media_news 預抓快取（週五 19:30 先抓好）。
Google 外部呼叫一律 fail-open：逾時/被擋即回空，分析照常跑。

用法：
    from src.analysis.news_evidence import news_evidence
    txt = news_evidence("2454")          # 自動查名稱、撈重大訊息 + Google News
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

import requests

_db = None


def _get_db():
    global _db
    if _db is None:
        from pymongo import MongoClient
        _db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))["tw_stock_analysis"]
    return _db


def _name_of(code: str) -> str | None:
    d = _get_db().taiwan_stock_info.find_one({"stock_id": code}, {"stock_name": 1})
    return d.get("stock_name") if d else None


def major_news_for(code: str, days: int = 14, limit: int = 5) -> list[str]:
    """該股近 days 天的 TWSE 官方重大訊息（subject + 摘要）。"""
    since = datetime.now() - timedelta(days=days)
    docs = list(_get_db().major_news.find(
        {"code": code, "date": {"$gte": since}},
        {"subject": 1, "detail": 1, "date": 1}).sort("date", -1).limit(limit))
    out = []
    for d in docs:
        subj = (d.get("subject") or "").strip()
        det = re.sub(r"\s+", " ", (d.get("detail") or "").strip())[:70]
        dt = d["date"].strftime("%m/%d") if d.get("date") else ""
        if subj:
            out.append(f"[{dt}官方訊息] {subj}" + (f"：{det}" if det else ""))
    return out


def google_titles(name: str, max_items: int = 4, timeout: int = 6) -> list[str]:
    """Google News RSS 原始標題（無前綴）。best-effort：任何錯誤/逾時回空。
    供 media_news_sync 預抓存純標題；一般查詢用 google_news_for。"""
    if not name:
        return []
    try:
        q = requests.utils.quote(f"{name} 股")
        url = (f"https://news.google.com/rss/search?q={q}"
               f"&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (X11; Linux) Chrome/120"})
        r.raise_for_status()
        # 用 regex 抽 <item> 內的 <title>，不進 XML parser → 避開 XXE/billion-laughs
        out = []
        for it in re.findall(r"<item>(.*?)</item>", r.text, re.DOTALL)[:max_items]:
            m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.DOTALL)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()
                if title:
                    out.append(title)
        return out
    except Exception:
        return []      # fail-open：新聞抓不到就當沒有，分析照常


def google_news_for(name: str, max_items: int = 4, timeout: int = 6) -> list[str]:
    """Google News RSS 媒體標題（加「[媒體]」前綴，供佐證文字）。"""
    return [f"[媒體] {t}" for t in google_titles(name, max_items, timeout)]


def media_news_for(code: str, max_items: int = 4, fresh_days: int = 8) -> list[str]:
    """讀 media_news 預抓快取的媒體標題（fresh_days 內才算新鮮，配合週抓節奏）。"""
    doc = _get_db().media_news.find_one({"code": code})
    if not doc:
        return []
    ts = doc.get("fetched_at")
    if not ts or ts < datetime.now() - timedelta(days=fresh_days):
        return []       # 太舊 → 當作沒有（寧缺勿給過期新聞）
    return [f"[媒體] {t}" for t in (doc.get("titles") or [])[:max_items] if t]


def news_evidence(code: str, name: str | None = None, days: int = 14) -> str:
    """組合新聞佐證文字（供餵給分析師）。無新聞則回空字串。"""
    name = name or _name_of(code)
    lines = major_news_for(code, days)
    if os.getenv("NEWS_GOOGLE", "1") != "0":
        # 小批 / 手動：即時抓最新，抓不到退回預抓快取
        lines += google_news_for(name) or media_news_for(code)
    else:
        # 全市場批次：只讀預抓快取（不即時外抓 Google，避免 2000 檔被限流）
        lines += media_news_for(code)
    if not lines:
        return ""
    body = "\n".join(f"- {x}" for x in lines[:8])
    return f"【近期新聞與重大訊息（{name or code}）】\n{body}"
