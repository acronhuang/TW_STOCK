#!/usr/bin/env python3
"""總經、政策、國際與產業新聞的原料累積：只增不改、每筆帶「何時可知」的時間戳（台北時間）。

目前沒有任何分析流程使用這份資料，只負責保存；之後要不要餵給總經分析師，先靠累積的資料量測再決定。
資料放在 tw_stock_analysis.wiki_raw（與公告、媒體標題同一個集合，已納入每日 mongodump 與異機備份），
stock_id 一律是空字串（不是個股資料）。兩種 kind：
  policy      官方來源 RSS：Fed（新聞稿、貨幣政策、談話）、中央銀行、行政院
  news_topic  Google News 主題查詢：國際與地緣（intl）、台灣政策（tw_policy）、產業（industry）

  macro_news_capture.py capture [--since YYYY-MM-DD] [--days N] [--dry-run]
  （統計請用 wiki_raw_capture.py stats）

沒有納入：經濟部、國發會（Cloudflare 擋 403，不繞過）、金管會（RSS 頁逾時，之後再試）、證交所新聞（多為個別公司上市審議公告，與總經無關）。
"""
import argparse
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.wiki_raw_capture import COLLECTION, _clean, _sha, insert_new, new_rows  # noqa: E402

TAIPEI = ZoneInfo("Asia/Taipei")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"
OFFICIAL_FEEDS = (
    ("fed_rss", "press_all", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("fed_rss", "press_monetary", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
    ("fed_rss", "speeches_and_testimony", "https://www.federalreserve.gov/feeds/speeches_and_testimony.xml"),
    ("cbc_rss", "all", "https://www.cbc.gov.tw/tw/rss-302-1.xml"),
    ("ey_rss", "news", "https://www.ey.gov.tw/RSS_Content.aspx?ModuleType=1&ModuleID=2&Type=Rss"),
)
GOOGLE_TOPICS = (
    ("intl", "出口管制 半導體"), ("intl", "關稅 台灣"), ("intl", "聯準會 利率"), ("intl", "地緣政治 台海"), ("intl", "美中 貿易"),
    ("tw_policy", "央行 理監事會"), ("tw_policy", "行政院 經濟政策"), ("tw_policy", "金管會 政策"),
)
PER_TOPIC_LIMIT = 30
GOOGLE_PAUSE = 1.0
MAX_GOOGLE_FAILURES = 3
FUTURE_TOLERANCE = timedelta(days=1)


def fetch_text(url, timeout=20):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.content.decode("utf-8-sig", errors="replace")


def _tag(block, name):
    match = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S | re.I)
    if not match:
        return ""
    text = re.sub(r"^\s*<!\[CDATA\[(.*?)\]\]>\s*$", r"\1", match.group(1), flags=re.S)
    return html.unescape(text).strip()


def parse_time(text):
    """RSS 的發布時間轉成台北時間（不帶時區）；看不懂回 None。沒有時區的 RFC 日期依 RFC 5322 視為 UTC。"""
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        return None
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(TAIPEI).replace(tzinfo=None, microsecond=0)


def parse_feed(text):
    """回 [{'title','link','summary','published'}]；沒有標題的項目略過。用 regex 而不進 XML 解析器，避開 XXE。"""
    items = []
    for block in re.findall(r"<item[\s>].*?</item>", text or "", re.S | re.I):
        title = _clean(re.sub(r"\s+", " ", _tag(block, "title")))
        if not title:
            continue
        summary = _clean(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _tag(block, "description"))))
        items.append({"title": title, "link": _tag(block, "link"), "summary": summary,
                      "published": parse_time(_tag(block, "pubDate") or _tag(block, "dc:date"))})
    return items


def news_row(source, kind, group, topic, item, captured_at):
    """一則新聞轉成 wiki_raw 的列。時間缺、看不懂或比抓取時間晚超過一天的，改用抓取時間（保守）並在 meta 註明。"""
    title = item["title"]
    published = item.get("published")
    fallback = published is None or published > captured_at + FUTURE_TOLERANCE
    available = captured_at if fallback else published
    identity = (item.get("link") or title) if kind == "policy" else title
    nkey = f"{source}|{kind}|{_sha(identity)[:16]}"
    content_sha = _sha(title + "\n" + (item.get("summary") or ""))
    return {
        "key": _sha(nkey + "|" + content_sha), "nkey": nkey, "source": source, "kind": kind,
        "stock_id": "", "name": topic, "title": title, "body": item.get("summary") or None, "event_date": None,
        "published_at": None if fallback else published, "available_at": available, "captured_at": captured_at,
        "content_sha": content_sha,
        "meta": {"group": group, "topic": topic, "link": item.get("link") or None, "date_fallback": fallback,
                 "publisher": title.rsplit(" - ", 1)[-1] if kind == "news_topic" and " - " in title else None},
    }


def google_url(query, days):
    # 時間窗是搜尋運算子，必須放在 q 裡；當成獨立參數時 Google 會忽略，回傳多年前的舊文章。
    return f"https://news.google.com/rss/search?q={quote(f'{query} when:{days}d')}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


def industry_topics(industries):
    out = []
    for name in industries:
        name = re.sub(r"\s+", "", name)
        short = re.sub(r"(工業|業)$", "", name)
        out.append(("industry", f"{short if len(short) >= 2 else name} 產業動態"))
    return out


def collect(now, since, days, fetch, sleep, industries):
    """回 (列, 各來源狀態)。官方來源逐一嘗試、失敗不影響其他；Google 連續失敗 3 次就停（被限流時不硬打）。"""
    rows, status = [], {}
    for source, label, url in OFFICIAL_FEEDS:
        name = f"{source}:{label}"
        try:
            items = parse_feed(fetch(url))
        except Exception as error:  # noqa: BLE001 - 單一來源失敗要記下來，其他來源照跑
            status[name] = f"失敗 {type(error).__name__}: {str(error)[:80]}"
            continue
        built = [news_row(source, "policy", "official", label, item, now) for item in items]
        kept = [r for r in built if r["available_at"] >= since]
        rows += kept
        status[name] = f"ok 看到 {len(items)} 則，納入 {len(kept)} 則" if items else "失敗 解析不到任何項目"
    failures, first = 0, True
    for group, topic in list(GOOGLE_TOPICS) + industry_topics(industries):
        name = f"google:{group}:{topic}"
        if failures >= MAX_GOOGLE_FAILURES:
            status[name] = "略過（連續失敗，停止查詢）"
            continue
        if not first:
            sleep(GOOGLE_PAUSE)
        first = False
        try:
            items = parse_feed(fetch(google_url(topic, days)))
        except Exception as error:  # noqa: BLE001
            failures += 1
            status[name] = f"失敗 {type(error).__name__}: {str(error)[:80]}"
            continue
        failures = 0
        oldest = now - timedelta(days=days + 1)
        items = [i for i in items if i["published"] is None or i["published"] >= oldest]
        items = sorted(items, key=lambda i: i["published"] or datetime.min, reverse=True)[:PER_TOPIC_LIMIT]
        rows += [news_row("google_news", "news_topic", group, topic, item, now) for item in items]
        status[name] = f"ok 取 {len(items)} 則"
    return rows, status


def capture(db, now, since, days=2, dry_run=False, fetch=fetch_text, sleep=time.sleep, industries=()):
    coll = db[COLLECTION]
    if not dry_run:
        coll.create_index("key", unique=True)
        coll.create_index([("stock_id", 1), ("available_at", 1)])
        coll.create_index([("kind", 1), ("available_at", 1)])
    rows, status = collect(now, since, days, fetch, sleep, industries)
    added = len(new_rows(coll, rows)) if dry_run else insert_new(coll, rows)
    return {"seen": len(rows), "added": added, "status": status}


def main(argv=None, db=None, now=datetime.now, fetch=fetch_text, sleep=time.sleep, industries=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--since", help="官方來源只納入此日之後的項目（預設今天往前 3 天；第一次回補可給較早的日期）")
    cap.add_argument("--days", type=int, default=2, help="Google News 查最近幾天")
    cap.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    db = db if db is not None else MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    moment = now()
    since = datetime.fromisoformat(args.since) if args.since else (moment - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    if industries is None:
        from src.ops.readonly_tools import INDUSTRIES
        industries = INDUSTRIES
    result = capture(db, moment, since, args.days, args.dry_run, fetch, sleep, industries)
    for name, text in result["status"].items():
        print(f"  {name}: {text}")
    print(f"看到 {result['seen']} 則，{'將新增' if args.dry_run else '新增'} {result['added']} 則")
    official_failed = any(text.startswith("失敗") for name, text in result["status"].items() if not name.startswith("google:"))
    return 1 if official_failed else 0


if __name__ == "__main__":
    sys.exit(main())
