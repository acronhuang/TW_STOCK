"""批次完成度：有 Ollama 產出（模型紀錄、結論、至少 2 張有效票）的比例。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

ALERT_SOURCE = "team_completion"
MIN_VALID_VOTES = 2


def is_complete(doc: dict) -> bool:
    votes = (doc.get("consensus") or {}).get("n") or 0
    return bool(doc.get("models")) and bool(doc.get("final_verdict")) and votes >= MIN_VALID_VOTES


def completion_stats(docs) -> dict:
    docs = list(docs)
    complete = sum(1 for doc in docs if is_complete(doc))
    return {"total": len(docs), "complete": complete, "ratio": complete / len(docs) if docs else 0.0}


def batch_stats(collection, day: date) -> dict:
    start = datetime.combine(day, time.min)
    query = {"date": {"$gte": start, "$lt": start + timedelta(days=1)}}
    return completion_stats(collection.find(query, {"models": 1, "final_verdict": 1, "consensus.n": 1}))


def alert_if_low(alerts, stats: dict, day: date, now: datetime, threshold: float = 0.9, min_docs: int = 20) -> bool:
    """比例低於門檻就告警(24h 去重)；恢復正常則消解舊告警。批次太小不評斷。"""
    if stats["total"] < min_docs:
        return False
    if stats["ratio"] >= threshold:
        alerts.update_many(
            {"source": ALERT_SOURCE, "resolved": {"$ne": True}},
            {"$set": {"resolved": True, "resolved_at": now, "resolved_reason": "auto: 完成度恢復正常"}},
        )
        return False
    if alerts.find_one({"source": ALERT_SOURCE, "resolved": {"$ne": True}, "ts": {"$gte": now - timedelta(hours=24)}}):
        return False
    alerts.insert_one(
        {
            "ts": now,
            "level": "warning",
            "source": ALERT_SOURCE,
            "message": (
                f"團隊分析 {day.isoformat()} 完成度偏低：{stats['complete']}/{stats['total']} "
                f"({stats['ratio']:.0%}) 有 Ollama 模型紀錄、結論與至少 {MIN_VALID_VOTES} 張有效票，門檻 {threshold:.0%}。"
            ),
            "resolved": False,
        }
    )
    return True
