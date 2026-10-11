"""相同來源、相同內容、尚未處理的告警，在期限內不重複寫入。"""
from __future__ import annotations

from datetime import datetime, timedelta

REMINDER = timedelta(days=7)


def insert_once(collection, doc: dict, *, now: datetime | None = None, within: timedelta = REMINDER) -> bool:
    """寫入成功回 True；已有相同的未處理告警（期限內）則略過回 False。超過期限視為提醒，再寫一則。"""
    now = now or datetime.now()
    duplicate = collection.find_one({"source": doc["source"], "message": doc["message"], "resolved": False,
                                     "ts": {"$gte": now - within}})
    if duplicate:
        return False
    collection.insert_one(doc)
    return True
