#!/usr/bin/env python3
"""LLM Wiki 的原始素材累積：只增不改、每筆帶「何時可知」的時間戳，供日後離線編譯 wiki 用。

目前沒有任何流程使用這份資料（不進評分、不進檢索），只負責保存。收的是兩種：
  announcement  重大訊息全文（來源 major_news；公告日加公告時間即為可知時間）
  media_title   Google News 標題（來源 media_news；那個集合每次抓取會整份覆寫，舊標題會消失）
資料放在 tw_stock_analysis.wiki_raw，因此納入每日 mongodump 與異機備份。

  wiki_raw_capture.py capture [--since YYYY-MM-DD] [--dry-run]   寫入新素材（可重複執行）
  wiki_raw_capture.py stats                                      看累積狀況
"""
import argparse
import hashlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from pymongo import MongoClient
from pymongo.errors import BulkWriteError

COLLECTION = "wiki_raw"
DUPLICATE_KEY = 11000
BACKFILL_FROM = "2026-04-01"  # major_news 最早的資料日


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def parse_published(day, time_text):
    """公告日加 HHMMSS 轉成時間；時間缺或不合法就用當日 23:59:59（保守：視為收盤後才可知）。"""
    base = day.replace(hour=0, minute=0, second=0, microsecond=0)
    digits = re.sub(r"\D", "", time_text or "")
    if len(digits) == 5:
        digits = "0" + digits
    if len(digits) == 6:
        hour, minute, second = int(digits[:2]), int(digits[2:4]), int(digits[4:])
        if hour < 24 and minute < 60 and second < 60:
            return base.replace(hour=hour, minute=minute, second=second)
    return base.replace(hour=23, minute=59, second=59)


def announcement_row(doc, captured_at):
    stock_id = str(doc.get("stock_id") or "").strip()
    day = doc.get("date")
    subject, detail = _clean(doc.get("subject")), _clean(doc.get("detail"))
    if not stock_id or not isinstance(day, datetime) or not (subject or detail):
        return None
    published = parse_published(day, doc.get("time"))
    source = doc.get("source") or "openapi"
    nkey = f"{source}|announcement|{stock_id}|{published:%Y%m%d%H%M%S}|{_sha(subject)[:12]}"
    content_sha = _sha(subject + "\n" + detail)
    fact_date = doc.get("fact_date")
    return {
        "key": _sha(nkey + "|" + content_sha), "nkey": nkey, "source": source, "kind": "announcement",
        "stock_id": stock_id, "name": doc.get("name") or "", "title": subject, "body": detail or None,
        "event_date": fact_date if isinstance(fact_date, datetime) else None,
        "published_at": published, "available_at": published, "captured_at": captured_at, "content_sha": content_sha,
        "meta": {"market": doc.get("market"), "clause": doc.get("clause"), "time": doc.get("time"), "origin": "major_news", "origin_id": str(doc.get("_id"))},
    }


def title_row(stock_id, name, title, fetched_at, captured_at):
    title = _clean(title)
    stock_id = str(stock_id or "").strip()
    if not title or not stock_id:
        return None
    nkey = f"google_news|media_title|{stock_id}|{_sha(title)[:16]}"
    content_sha = _sha(title)
    publisher = title.rsplit(" - ", 1)[-1] if " - " in title else None
    return {
        "key": _sha(nkey + "|" + content_sha), "nkey": nkey, "source": "google_news", "kind": "media_title",
        "stock_id": stock_id, "name": name or "", "title": title, "body": None, "event_date": None, "published_at": None,
        "available_at": fetched_at or captured_at, "captured_at": captured_at, "content_sha": content_sha,
        "meta": {"publisher": publisher, "origin": "media_news"},
    }


def _unique(rows):
    seen, out = set(), []
    for row in rows:
        if row["key"] not in seen:
            seen.add(row["key"])
            out.append(row)
    return out


def new_rows(coll, rows, chunk=500):
    """回還沒寫入過的列（依 key 比對，並去掉同一批內的重複）。"""
    fresh = []
    for i in range(0, len(rows), chunk):
        batch = _unique(rows[i:i + chunk])
        have = {d["key"] for d in coll.find({"key": {"$in": [r["key"] for r in batch]}}, {"key": 1})}
        fresh += [r for r in batch if r["key"] not in have]
    return fresh


def insert_new(coll, rows, chunk=500):
    """只新增、不更新；回實際新增筆數。同時有別的程序寫入造成的重複鍵會被容忍，其他寫入錯誤照拋。"""
    inserted = 0
    for i in range(0, len(rows), chunk):
        batch = new_rows(coll, rows[i:i + chunk], chunk)
        if not batch:
            continue
        try:
            coll.insert_many(batch, ordered=False)
            inserted += len(batch)
        except BulkWriteError as error:
            errors = error.details.get("writeErrors", [])
            if any(e.get("code") != DUPLICATE_KEY for e in errors):
                raise
            inserted += len(batch) - len(errors)
    return inserted


def collect(db, since, now):
    announcements = [r for r in (announcement_row(d, now) for d in db["major_news"].find({"date": {"$gte": since}})) if r]
    titles = []
    for doc in db["media_news"].find({}):
        for title in doc.get("titles") or []:
            if isinstance(title, str):
                row = title_row(doc.get("stock_id"), doc.get("name"), title, doc.get("fetched_at"), now)
                if row:
                    titles.append(row)
    return announcements, titles


def capture(db, since, now, dry_run=False):
    """回 {'announcement': (看到, 新增), 'media_title': (看到, 新增)}；dry_run 只數、不寫。"""
    coll = db[COLLECTION]
    if not dry_run:
        coll.create_index("key", unique=True)
        coll.create_index([("stock_id", 1), ("available_at", 1)])
        coll.create_index([("kind", 1), ("available_at", 1)])
    announcements, titles = collect(db, since, now)
    result = {}
    for kind, rows in (("announcement", announcements), ("media_title", titles)):
        added = len(new_rows(coll, rows)) if dry_run else insert_new(coll, rows)
        result[kind] = (len(rows), added)
    return result


def stats(coll):
    """每個 (來源, 種類) 的筆數、涵蓋代號數與可知時間範圍，以及每月新增筆數。"""
    groups = defaultdict(lambda: {"n": 0, "stocks": set(), "lo": None, "hi": None})
    months = defaultdict(int)
    for doc in coll.find({}, {"source": 1, "kind": 1, "stock_id": 1, "available_at": 1}):
        g = groups[(doc["source"], doc["kind"])]
        g["n"] += 1
        g["stocks"].add(doc["stock_id"])
        when = doc["available_at"]
        g["lo"] = when if g["lo"] is None or when < g["lo"] else g["lo"]
        g["hi"] = when if g["hi"] is None or when > g["hi"] else g["hi"]
        months[f"{when:%Y-%m}"] += 1
    return {"groups": {k: {"n": v["n"], "stocks": len(v["stocks"]), "lo": v["lo"], "hi": v["hi"]} for k, v in groups.items()},
            "months": dict(sorted(months.items()))}


def main(argv=None, db=None, now=datetime.now):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--since", help=f"公告日起算（預設今天往前 3 天；第一次回補用 {BACKFILL_FROM}）")
    cap.add_argument("--dry-run", action="store_true")
    sub.add_parser("stats")
    args = parser.parse_args(argv)
    db = db if db is not None else MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    moment = now()
    if args.cmd == "stats":
        report = stats(db[COLLECTION])
        for (source, kind), g in sorted(report["groups"].items()):
            print(f"{source:12s} {kind:13s} {g['n']:8d} 筆  {g['stocks']:5d} 檔  {g['lo']:%Y-%m-%d} ~ {g['hi']:%Y-%m-%d}")
        print("每月（以可知時間計）:", "  ".join(f"{m} {n}" for m, n in report["months"].items()) or "無")
        return 0
    since = datetime.fromisoformat(args.since) if args.since else (moment - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    result = capture(db, since, moment, dry_run=args.dry_run)
    for kind, (seen, added) in result.items():
        print(f"{kind:13s} 看到 {seen:6d}  {'將新增' if args.dry_run else '新增'} {added:6d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
