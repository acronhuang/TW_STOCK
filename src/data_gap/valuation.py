"""官方 PE/PB/殖利率（TWSE BWIBBU_d、TPEX peQryDate）按日期回補，以及「官方來源某日殘缺」的偵測。"""
from __future__ import annotations

import statistics
from datetime import datetime

import requests

OFFICIAL_SOURCES = {"TWSE_BWIBBU", "TPEX_PERATIO"}
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
THIN_RATIO = 0.5
NEIGHBOURS = 10
MIN_NEIGHBOURS = 5


def _number(value) -> float | None:
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "--", "---", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_twse(payload: dict, day: datetime) -> list[dict]:
    if payload.get("stat") != "OK":
        return []
    rows = []
    for row in payload.get("data") or []:
        symbol = str(row[0]).strip()
        if not symbol.isdigit():
            continue
        rows.append({"symbol": symbol, "date": day, "pe_ratio": _number(row[5]), "pb_ratio": _number(row[6]),
                     # 每日流程用的 OpenAPI 把「不發股利」的 0.00 殖利率當空值；這裡對齊，避免同一欄位兩種口徑。
                     "dividend_yield": _number(row[3]) or None, "data_source": "TWSE_BWIBBU"})
    return rows


def parse_tpex(payload: dict, day: datetime) -> list[dict]:
    tables = payload.get("tables") or []
    rows = []
    for row in (tables[0].get("data") if tables else None) or []:
        symbol = str(row[0]).strip()
        if not symbol.isdigit():
            continue
        rows.append({"symbol": symbol, "date": day, "pe_ratio": _number(row[2]), "pb_ratio": _number(row[6]),
                     "dividend_yield": _number(row[5]), "dividend_per_share": _number(row[3]),
                     "data_source": "TPEX_PERATIO"})
    return rows


def fetch(day: datetime, get=requests.get) -> dict[str, list[dict]]:
    twse = get(TWSE_URL, params={"date": f"{day:%Y%m%d}", "selectType": "ALL", "response": "json"},
               headers=_HEADERS, timeout=30)
    twse.raise_for_status()
    tpex = get(TPEX_URL, params={"date": f"{day:%Y/%m/%d}", "response": "json"}, headers=_HEADERS, timeout=30)
    tpex.raise_for_status()
    return {"TWSE_BWIBBU": parse_twse(twse.json(), day), "TPEX_PERATIO": parse_tpex(tpex.json(), day)}


# PE/PB 由 evening_pipeline 的 backfill_pe_pb_factors 每晚用財報對所有 stock_factors 重算並覆寫（會 unset 算不出的值），
# 官方端點的 PE/PB 寫了也會被蓋掉；因此只回補官方獨有的欄位。
WRITE_FIELDS = ("dividend_yield", "dividend_per_share", "data_source")


def upsert(collection, rows: list[dict], now: datetime):
    """只寫官方獨有的非空欄位，依 (symbol, date) upsert；不寫 PE/PB，也不用 None 清掉既有值。"""
    from pymongo import UpdateOne

    operations = []
    for row in rows:
        fields = {k: row[k] for k in WRITE_FIELDS if row.get(k) is not None}
        fields["updated_at"] = now
        operations.append(UpdateOne({"symbol": row["symbol"], "date": row["date"]}, {"$set": fields}, upsert=True))
    return collection.bulk_write(operations, ordered=False)


def thin_days(counts: dict[str, dict], days: list[str]) -> list[tuple[str, str, int, int]]:
    """(日, 來源, 筆數, 鄰近中位數)：官方來源某日筆數低於鄰近交易日中位數的一半。鄰居不足不判。"""
    ordered = sorted(days)
    found = []
    for source in sorted(OFFICIAL_SOURCES):
        series = {day: (counts.get(day) or {}).get(source, 0) for day in ordered}
        for index, day in enumerate(ordered):
            neighbours = [series[d] for d in ordered[max(0, index - NEIGHBOURS):index] + ordered[index + 1:index + 1 + NEIGHBOURS]]
            if len(neighbours) < MIN_NEIGHBOURS:
                continue
            median = int(statistics.median(neighbours))
            if median > 0 and series[day] < median * THIN_RATIO:
                found.append((day, source, series[day], median))
    return sorted(found)
