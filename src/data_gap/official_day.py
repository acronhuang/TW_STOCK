"""官方按日期資料（TWSE rwd、TPEX www）→ odd_lot_trading / after_hours_trading / foreign_top20。

OpenAPI 的「最新日」端點多數沒有資料日期，且交易日 17:30 抓到的是前一交易日的資料（2026-10-11 以官方按日期資料
逐表證實：零股、盤後定價、外資 Top20 的標記日都早一天）。這裡改用帶明確日期的官方端點，回傳的資料日必須等於
請求日才採用，所以不會再把別天的資料標成這一天。
"""
from __future__ import annotations

import time
from datetime import datetime

COLLECTION = {"odd": "odd_lot_trading", "after_hours": "after_hours_trading", "foreign_top20": "foreign_top20"}
SOURCES = {"odd": ("twse_odd", "tpex_odd"), "after_hours": ("twse_after_hours", "tpex_after_hours"),
           "foreign_top20": ("foreign_top20",)}

_TRADE = {
    "twse_odd": ("證券代號", "證券名稱", "成交股數", "成交金額", "成交價", "TWSE"),
    "twse_after_hours": ("證券代號", "證券名稱", "成交數量", "成交金額", "成交價", "TWSE"),
    "tpex_after_hours": ("代號", "名稱", "成交張數", "成交金額", "成交價(元)", "TPEX"),
    "tpex_odd": ("代號", "名稱", "成交股數", "成交金額", "成交價格(元)", "TPEX"),
}
_TWSE_RWD = "https://www.twse.com.tw/rwd/zh/"
_TPEX_WWW = "https://www.tpex.org.tw/www/zh-tw/afterTrading/"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.tpex.org.tw/"}


def _int(value) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return 0


def _float(value) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return 0.0


def _table(source: str, payload: dict) -> tuple[list[str], list[list]] | None:
    if str(payload.get("stat", "")).lower() != "ok":
        return None
    if source.startswith("tpex"):
        tables = payload.get("tables") or []
        return ([f.strip() for f in tables[0].get("fields") or []], tables[0].get("data") or []) if tables else None
    return [f.strip() for f in payload.get("fields") or []], payload.get("data") or []


def parse(source: str, payload: dict, day: datetime) -> list[dict]:
    """回傳的資料日不等於 day（或狀態不是 ok）就視為沒有資料。"""
    if payload.get("date") != day.strftime("%Y%m%d"):
        return []
    table = _table(source, payload)
    if table is None:
        return []
    fields, data = table
    docs = []
    for row in data:
        cells = dict(zip(fields, row))
        if source == "foreign_top20":
            code = str(cells.get("證券代號", "")).strip()
            if code:
                docs.append({"rank": _int(cells.get("排行")), "stock_id": code, "name": str(cells.get("證券名稱", "")).strip(),
                             "shares_held": _int(cells.get("全體外資及陸資持有股數")),
                             "shares_held_pct": _float(cells.get("全體外資及陸資持股比率")),
                             "upper_limit": _float(cells.get("法令投資上限比率")), "date": day})
            continue
        code_key, name_key, volume_key, value_key, close_key, market = _TRADE[source]
        code = str(cells.get(code_key, "")).strip()
        if code:
            docs.append({"stock_id": code, "name": str(cells.get(name_key, "")).strip(), "volume": _int(cells.get(volume_key)),
                         "value": _int(cells.get(value_key)), "close": _float(cells.get(close_key)),
                         "date": day, "market": market})
    return docs


def fetch(source: str, day: datetime | None = None) -> dict:
    """day=None 取最新（僅 TWSE 端點，用來讀資料日）。"""
    import requests

    ymd = day.strftime("%Y%m%d") if day else ""
    slash = day.strftime("%Y/%m/%d") if day else ""
    if source == "twse_odd":
        response = requests.get(f"{_TWSE_RWD}afterTrading/TWT53U?date={ymd}&response=json", headers=_HEADERS, timeout=40)
    elif source == "twse_after_hours":
        response = requests.get(f"{_TWSE_RWD}afterTrading/BFT41U?date={ymd}&selectType=ALL&response=json", headers=_HEADERS, timeout=60)
    elif source == "foreign_top20":
        response = requests.get(f"{_TWSE_RWD}fund/MI_QFIIS_sort_20?date={ymd}&response=json", headers=_HEADERS, timeout=40)
    elif source == "tpex_after_hours":
        response = requests.post(f"{_TPEX_WWW}fixPricing", data={"date": slash, "id": "", "response": "json"}, headers=_HEADERS, timeout=60)
    else:
        response = requests.post(f"{_TPEX_WWW}odd", data={"type": "Daily", "date": slash, "id": "", "response": "json"},
                                 headers=_HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def latest_day(kind: str) -> datetime | None:
    payload = fetch(SOURCES[kind][0])
    text = payload.get("date")
    return datetime.strptime(text, "%Y%m%d") if text else None


def docs_for(kind: str, day: datetime, pause: float = 1.2) -> list[dict]:
    docs = []
    for source in SOURCES[kind]:
        for attempt in range(2):  # 實測 TPEX 會偶發逾時，重試一次；仍失敗才略過，其他來源照寫
            try:
                docs += parse(source, fetch(source, day), day)
                break
            except Exception:  # noqa: BLE001
                time.sleep(pause)
        time.sleep(pause)
    return docs


def upsert(collection, docs: list[dict], now: datetime):
    from pymongo import UpdateOne

    if not docs:
        return None
    operations = [UpdateOne({"stock_id": d["stock_id"], "date": d["date"]}, {"$set": {**d, "updated_at": now}}, upsert=True)
                  for d in docs]
    return collection.bulk_write(operations, ordered=False)


def sync_latest(db, kind: str, now: datetime) -> int:
    """寫入該類別官方最新資料日（TWSE 與 TPEX 同一天）；回傳寫入筆數。"""
    day = latest_day(kind)
    if day is None:
        return 0
    docs = docs_for(kind, day)
    upsert(db[COLLECTION[kind]], docs, now)
    return len(docs)
