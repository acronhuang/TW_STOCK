import re
import statistics
from datetime import datetime

TWT49U = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
REQUIRED = {"資料日期", "股票代號", "除權息前收盤價", "除權息參考價", "權/息"}
MAX_FACTOR = 1.5  # backfill_adj_close 只套用 0 < factor < 1.5


def _number(text):
    return float(str(text).replace(",", "").strip())


def _date(text):
    match = re.fullmatch(r"\s*(\d{2,3})(?:年|/)(\d{1,2})(?:月|/)(\d{1,2})日?\s*", str(text))
    if match is None:
        raise ValueError(f"unrecognized official date: {text!r}")
    year, month, day = (int(part) for part in match.groups())
    return datetime(year + 1911, month, day)


def parse_exright_factors(payload, start, end):
    """TWSE 除權息計算結果表 → 還原係數候選。factor = 除權息參考價 / 除權息前收盤價（事件日之前的價 × factor）。"""
    if payload.get("stat") != "OK":
        raise ValueError("official exright table did not return OK")
    if str(payload.get("strDate")) != start.strftime("%Y%m%d") or str(payload.get("endDate")) != end.strftime("%Y%m%d"):
        raise ValueError("official response date range does not match request")
    fields = payload.get("fields", [])
    if not REQUIRED.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official exright schema changed")
    events, skipped, seen = [], [], set()
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official exright row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol, stamp = str(row["股票代號"]).strip(), _date(row["資料日期"])
        if not start <= stamp <= end or (symbol, stamp) in seen:
            raise ValueError("official exright row outside requested dates or duplicated")
        seen.add((symbol, stamp))
        try:
            prior, reference = _number(row["除權息前收盤價"]), _number(row["除權息參考價"])
        except ValueError:
            skipped.append({"stock_id": symbol, "ex_date": stamp, "reason": "unreadable_price"})
            continue
        if prior <= 0 or reference <= 0 or not reference / prior < MAX_FACTOR:
            skipped.append({"stock_id": symbol, "ex_date": stamp, "reason": "factor_out_of_range"})
            continue
        events.append({"stock_id": symbol, "ex_date": stamp, "factor": reference / prior, "prev_close": prior,
                       "ref_price": reference, "kind": str(row["權/息"]).strip()})
    return {"events": sorted(events, key=lambda event: (event["ex_date"], event["stock_id"])), "skipped": skipped}


def missing_factors(events, existing, priced):
    """官方事件中，還原係數表尚無 (stock_id, ex_date) 且該代號在價格表有資料者。"""
    return [event for event in events if event["stock_id"] in priced and (event["stock_id"], event["ex_date"]) not in existing]


def agreement(events, existing_factors):
    """與既有（FinMind 股利明細推算）係數同事件者的差異，用來檢驗官方公式。existing_factors: {(stock_id, ex_date): factor}"""
    diffs = [abs(event["factor"] - existing_factors[(event["stock_id"], event["ex_date"])])
             for event in events if (event["stock_id"], event["ex_date"]) in existing_factors]
    if not diffs:
        return {"overlap": 0, "median_abs_diff": None, "over_half_percent": 0}
    return {"overlap": len(diffs), "median_abs_diff": statistics.median(diffs), "over_half_percent": sum(d > 0.005 for d in diffs)}
