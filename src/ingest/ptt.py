"""PTT Stock 板每日討論熱度：走訪最近幾天的列表頁，統計個股提及數、推文數與標題情緒。

只抓列表頁（約每天 40 頁），不逐檔搜尋；標題含股票代號或名稱即算提及。
"""
from __future__ import annotations

import html as html_lib
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from src.ingest.text_sentiment import score_text

BOARD_URL = "https://www.ptt.cc/bbs/Stock/index.html"
_ORIGIN = "https://www.ptt.cc"
SOURCE = "ptt"
_SHORT_NAME_TAGS = ("標的",)   # 兩字股名常是一般詞彙（「數字」「世界」「大量」），只在作者刻意標示標的的文章採計；其它文章需帶代號
_TAG_ADJUSTMENT = {"多": 20.0, "空": -20.0}
_TOP_POSTS = 5

_ENTRY = re.compile(r'<div class="r-ent">(.*?)(?=<div class="r-ent">|\Z)', re.S)
_NREC = re.compile(r'<div class="nrec">\s*(?:<span[^>]*>([^<]*)</span>)?', re.S)
_TITLE = re.compile(r'<div class="title">\s*<a href="([^"]+)">([^<]*)</a>', re.S)
_AUTHOR = re.compile(r'<div class="author">([^<]*)</div>')
_DATE = re.compile(r'<div class="date">\s*(\d{1,2})/(\d{1,2})\s*</div>')
_PREVIOUS = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>\s*&lsaquo;')
_TAG = re.compile(r"^\s*(?:Re:\s*)?\[([^\]]+)\]")
_DIRECTION = re.compile(r"\[(多|空)\]|\s(多|空)\s*$")   # 「[多]」「[空]」或 [標的] 文章常見的結尾「 ... 多」
_CODE = re.compile(r"(?<![\d.$,])(\d{4})(?![\d年月日/%元點張股.])")


def push_count(text: str) -> int:
    text = (text or "").strip()
    if text == "爆":
        return 100
    if text == "XX":
        return -100
    if re.fullmatch(r"X\d", text):
        return -10 * int(text[1])
    return int(text) if text.isdigit() else 0


def _post_date(month: int, day: int, today: date) -> date | None:
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    return candidate if candidate <= today + timedelta(days=1) else date(today.year - 1, month, day)


def parse_index(page_html: str, today: date) -> tuple[list[dict], str | None]:
    previous = _PREVIOUS.search(page_html)
    body = page_html.split('<div class="r-list-sep">')[0]   # 分隔線之後是置頂公告
    posts = []
    for entry in _ENTRY.findall(body):
        title_match, day = _TITLE.search(entry), _DATE.search(entry)
        if not title_match or not day:
            continue
        link, title = title_match.groups()
        post_day = _post_date(int(day.group(1)), int(day.group(2)), today)
        if post_day is None:
            continue
        nrec, author = _NREC.search(entry), _AUTHOR.search(entry)
        posts.append({"title": html_lib.unescape(title).strip(), "url": _ORIGIN + link,
                      "author": author.group(1).strip() if author else "", "date": post_day,
                      "push": push_count(nrec.group(1) if nrec and nrec.group(1) else "")})
    return posts, (_ORIGIN + previous.group(1)) if previous else None


class Matcher:
    """標題 → 提及的股票代號。長名稱優先並從標題移除，避免「中鋼構」同時算成「中鋼」。"""

    def __init__(self, universe: list[tuple[str, str]]):
        self.codes = {code for code, _ in universe}
        self.names = sorted(((name, code) for code, name in universe if len(name) >= 2), key=lambda x: -len(x[0]))

    def match(self, title: str) -> set[str]:
        found = {code for code in _CODE.findall(title) if code in self.codes}
        tag = _TAG.match(title)
        allow_short = bool(tag) and tag.group(1) in _SHORT_NAME_TAGS
        remaining = title
        for name, code in self.names:
            if len(name) < 3 and not allow_short:
                continue
            if name in remaining:
                found.add(code)
                remaining = remaining.replace(name, "\0")
        return found


def _post_score(title: str) -> float:
    score = score_text(title)
    direction = _DIRECTION.search(title)
    if direction:
        score += _TAG_ADJUSTMENT[direction.group(1) or direction.group(2)]
    return max(-100.0, min(100.0, score))


def aggregate(posts: list[dict], matcher: Matcher) -> list[dict]:
    groups: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for post in posts:
        for code in matcher.match(post["title"]):
            groups[(code, post["date"])].append(post)
    rows = []
    for (code, day), items in sorted(groups.items()):
        scores = [_post_score(p["title"]) for p in items]
        top = sorted(items, key=lambda p: -p["push"])[:_TOP_POSTS]
        rows.append({
            "stock_id": code, "date": datetime(day.year, day.month, day.day), "source": SOURCE,
            "mentions": len(items), "push_sum": sum(p["push"] for p in items),
            "bullish": sum(1 for s in scores if s > 0), "bearish": sum(1 for s in scores if s < 0),
            "score": round(sum(scores) / len(scores), 1),
            "top_posts": [{"title": p["title"], "url": p["url"], "push": p["push"]} for p in top],
        })
    return rows


def buzz_ratio(mentions: int, previous: list[int], min_days: int = 5) -> float | None:
    """熱度暴增指數 = (今日提及 + 1) / (過去平均提及 + 1)；歷史不足 min_days 天不判斷。"""
    if len(previous) < min_days:
        return None
    return round((mentions + 1) / (sum(previous) / len(previous) + 1), 2)


def attach_buzz(rows: list[dict], history: dict, crawled_dates: set, window: int = 20, min_days: int = 5) -> list[dict]:
    """history: {(stock_id, date): mentions}；crawled_dates: 已爬過的日期（沒文件的日子以 0 計）。"""
    all_dates = sorted(set(crawled_dates) | {r["date"] for r in rows})
    known = {**history, **{(r["stock_id"], r["date"]): r["mentions"] for r in rows}}
    for row in rows:
        earlier = [d for d in all_dates if d < row["date"]][-window:]
        row["buzz_ratio"] = buzz_ratio(row["mentions"], [known.get((row["stock_id"], d), 0) for d in earlier], min_days)
    return rows


def crawl(fetch, *, today: date, days_back: int = 2, sleep=time.sleep, pause: float = 1.0, max_pages: int = 120) -> list[dict]:
    """由最新頁往回走，直到整頁都早於截止日；回傳截止日以來的所有文章。"""
    cutoff = today - timedelta(days=days_back - 1)
    kept: list[dict] = []
    url: str | None = BOARD_URL
    for index in range(max_pages):
        if index:
            sleep(pause)
        posts, previous = parse_index(fetch(url), today)
        kept += [p for p in posts if p["date"] >= cutoff]
        if posts and all(p["date"] < cutoff for p in posts):
            break
        if not previous:
            break
        url = previous
    return kept


def fetch_page(url: str) -> str:
    import requests

    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (tw-stock research crawler)",
                                                      "Cookie": "over18=1"})
    response.raise_for_status()
    return response.text
