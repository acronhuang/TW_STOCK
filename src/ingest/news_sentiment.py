"""新聞標題情緒每日入庫：每檔每日一筆（標題數、正負面數、平均情緒分數、前 10 則標題）。"""
from __future__ import annotations

from datetime import datetime

from src.ingest.text_sentiment import label, score_text

SOURCE = "google_news"
_KEPT_TITLES = 10


def summarize(titles: list[str]) -> dict:
    scores = [score_text(title) for title in titles]
    average = round(sum(scores) / len(scores), 1) if scores else None
    return {
        "count": len(titles), "positive": sum(1 for s in scores if s > 0), "negative": sum(1 for s in scores if s < 0),
        "neutral": sum(1 for s in scores if s == 0), "score": average, "label": label(average),
        "titles": list(titles[:_KEPT_TITLES]),
    }


def build_doc(stock_id: str, name: str, titles: list[str], when: datetime, now: datetime) -> dict:
    return {"stock_id": stock_id, "date": datetime(when.year, when.month, when.day), "source": SOURCE,
            "name": name, **summarize(titles), "updated_at": now}


def upsert(collection, docs: list[dict]):
    from pymongo import UpdateOne

    if not docs:
        return None
    operations = [UpdateOne({"stock_id": d["stock_id"], "date": d["date"], "source": d["source"]},
                            {"$set": d}, upsert=True) for d in docs]
    return collection.bulk_write(operations, ordered=False)


def focus_codes(positions: list[dict], core: dict | None, vcp: list[dict]) -> list[str]:
    """每日追蹤名單：持倉優先，其次核心池，再其次最新 VCP 候選；去重保序。"""
    ordered = [p.get("symbol") for p in positions]
    ordered += [s.get("symbol") for s in ((core or {}).get("stocks") or [])]
    ordered += [v.get("symbol") for v in vcp]
    seen, out = set(), []
    for code in ordered:
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out
