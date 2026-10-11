"""失敗項補跑：找出本來該由 Ollama 產出、卻留下錯誤訊息的文件。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from src.moe.guard import is_failed_report


def needs_retry(doc: dict) -> bool:
    """有角色報告是錯誤訊息，或顧問整合失敗／被略過。尚未整合(advisor 為空)只是待辦，不算失敗。"""
    if any(is_failed_report(text) for text in (doc.get("reports") or {}).values()):
        return True
    return is_failed_report(doc.get("advisor"))


def is_fallback_verdict(doc: dict) -> bool:
    """Ollama 全失敗後，合議以預設值湊出的結論：零有效票且顧問整合被略過／失敗。"""
    consensus = doc.get("consensus") or {}
    return bool(doc.get("final_verdict")) and consensus.get("n") == 0 and is_failed_report(doc.get("advisor"))


def find_retry_targets(collection, today: date, days: int = 2, only_date: date | None = None) -> dict[date, list[dict]]:
    """分析日 -> 需補跑的標的。指定 only_date 時只看那一天；否則看最近 days 天。"""
    if only_date is not None:
        start, end = only_date, only_date + timedelta(days=1)
    else:
        start, end = today - timedelta(days=days), today + timedelta(days=1)
    query = {
        "date": {"$gte": datetime.combine(start, time.min), "$lt": datetime.combine(end, time.min)},
        "reports": {"$exists": True, "$ne": {}},
    }
    found: dict[date, list[dict]] = defaultdict(list)
    for document in collection.find(query, {"symbol": 1, "name": 1, "date": 1, "reports": 1, "advisor": 1}):
        if needs_retry(document):
            found[document["date"].date()].append(
                {"symbol": str(document["symbol"]), "name": document.get("name") or ""}
            )
    return dict(sorted(found.items()))
