"""券資比 = 融券餘額 / 融資餘額 × 100，寫入 stock_factors.short_margin_ratio。"""
from __future__ import annotations

from datetime import datetime

FIELD = "short_margin_ratio"


def _number(value) -> float | None:
    if value is None:
        return None
    if hasattr(value, "to_decimal"):
        value = value.to_decimal()
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def short_margin_ratio(margin_balance, short_balance) -> float | None:
    margin, short = _number(margin_balance), _number(short_balance)
    if not margin or short is None:
        return None
    return round(short / margin * 100, 2)


def apply_day(collection, day: datetime, margin_docs: list[dict]):
    """只更新既有的 (symbol, date) 因子文件；算不出時清掉舊值，避免殘留過期數字。"""
    from pymongo import UpdateOne

    operations = []
    for doc in margin_docs:
        code = str(doc.get("code") or "").strip()
        if not code:
            continue
        ratio = short_margin_ratio(doc.get("margin_balance"), doc.get("short_balance"))
        change = {"$set": {FIELD: ratio}} if ratio is not None else {"$unset": {FIELD: ""}}
        operations.append(UpdateOne({"symbol": code, "date": day}, change, upsert=False))
    return collection.bulk_write(operations, ordered=False) if operations else None
