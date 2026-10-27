import re
from datetime import datetime

TWTCAU = "https://www.twse.com.tw/rwd/zh/split/TWTCAU"
REQUIRED = {"恢復買賣日期", "ETF代號", "分割(反分割)", "停止買賣前收盤價格", "恢復買賣參考價"}
MAX_RATIO = 20  # backfill_adj_close 只套用 0 < ratio < 20


def _price(text):
    return float(str(text).replace(",", "").strip())


def _roc_date(text):
    match = re.fullmatch(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})\s*", str(text))
    if match is None:
        raise ValueError(f"unrecognized official date: {text!r}")
    year, month, day = (int(part) for part in match.groups())
    return datetime(year + 1911, month, day)


def parse_split_table(payload):
    """TWSE 官方 ETF 分割/反分割恢復買賣參考價表 → corporate_actions 文件。

    ratio = 恢復買賣參考價 / 停止買賣前收盤價（事件日之前的價 × ratio 即為還原價；分割 < 1、反分割 > 1）。
    """
    if payload.get("stat") != "OK":
        raise ValueError("official split table did not return OK")
    fields = payload.get("fields", [])
    if not REQUIRED.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official split table schema changed")
    events, seen = [], set()
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official split row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol, stamp = str(row["ETF代號"]).strip(), _roc_date(row["恢復買賣日期"])
        pre_close, reference = _price(row["停止買賣前收盤價格"]), _price(row["恢復買賣參考價"])
        if pre_close <= 0 or reference <= 0 or (symbol, stamp) in seen:
            raise ValueError("invalid or duplicated official split row")
        seen.add((symbol, stamp))
        ratio = round(reference / pre_close, 6)
        if not 0 < ratio < MAX_RATIO:
            raise ValueError(f"split ratio {ratio} outside the supported range")
        kind = str(row["分割(反分割)"]).strip()
        if kind and (kind == "分割") != (ratio < 1):
            raise ValueError("official split kind disagrees with the price ratio")
        events.append({"symbol": symbol, "event_date": stamp, "type": "分割" if ratio < 1 else "反分割",
                       "reason": "ETF受益權單位分割/反分割(官方恢復買賣參考價)", "pre_close": pre_close,
                       "ref_price": reference, "ratio": ratio, "source": "TWSE_TWTCAU"})
    return sorted(events, key=lambda event: (event["event_date"], event["symbol"]))


def missing_actions(events, existing):
    """官方事件中，corporate_actions 尚無 (symbol, event_date) 紀錄者。existing: {(symbol, event_date)}。"""
    return [event for event in events if (event["symbol"], event["event_date"]) not in existing]
