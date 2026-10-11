"""興櫃每日行情：TPEX OpenAPI tpex_esb_latest_statistics 只給最新交易日，無歷史端點，只能從開始收集日起累積。"""
from __future__ import annotations

from datetime import datetime

URL = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"
SOURCE = "TPEX_ESB"
_USER_AGENT = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}


def _roc_date(text) -> datetime | None:
    text = str(text or "").strip()
    if len(text) != 7 or not text.isdigit():
        return None
    try:
        return datetime(int(text[:3]) + 1911, int(text[3:5]), int(text[5:]))
    except ValueError:
        return None


def _number(text) -> float | None:
    text = str(text if text is not None else "").replace(",", "").strip()
    if text in ("", "--", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _quantity(text) -> int | None:
    number = _number(text)
    return None if number is None else int(number)


def parse(rows: list[dict], now: datetime) -> list[dict]:
    docs = []
    for row in rows:
        stock_id = str(row.get("SecuritiesCompanyCode") or "").strip()
        day = _roc_date(row.get("Date"))
        if not stock_id or day is None:
            continue
        docs.append({
            "stock_id": stock_id, "date": day, "name": str(row.get("CompanyName") or "").strip(),
            "last_price": _number(row.get("LatestPrice")), "avg_price": _number(row.get("Average")),
            "prev_avg_price": _number(row.get("PreviousAveragePrice")),
            "high": _number(row.get("Highest")), "low": _number(row.get("Lowest")),
            "volume": _quantity(row.get("TransactionVolume")),
            "bid_price": _number(row.get("BuyingPrice")), "bid_qty": _quantity(row.get("BuyingQuantity")),
            "ask_price": _number(row.get("SellingPrice")), "ask_qty": _quantity(row.get("SellingQuantity")),
            "data_source": SOURCE, "updated_at": now,
        })
    return docs


def fetch() -> list[dict]:
    import requests

    response = requests.get(URL, headers=_USER_AGENT, timeout=40)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def upsert(collection, docs: list[dict]):
    from pymongo import UpdateOne

    if not docs:
        return None
    operations = [UpdateOne({"stock_id": d["stock_id"], "date": d["date"]}, {"$set": d}, upsert=True) for d in docs]
    return collection.bulk_write(operations, ordered=False)
