import html
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .data import validate_symbols
from .registry import file_hash, save_new
from .sources import number, source_date

SPLIT = "https://www.twse.com.tw/rwd/zh/split/TWTCAU"
NO_LIMIT_UPPER, NO_LIMIT_LOWER = Decimal("9999.95"), Decimal("0.01")
TICK = Decimal("0.01")


def parse_split_table(payload, start, end):
    start, end = source_date(start), source_date(end)
    if payload.get("stat") != "OK":
        raise ValueError("official split table did not return OK")
    fields = payload.get("fields", [])
    required = {"恢復買賣日期", "ETF代號", "分割(反分割)", "停止買賣前收盤價格", "恢復買賣參考價", "漲停價格", "跌停價格"}
    if not required.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official split table schema changed")
    events, seen = [], set()
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official split row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol, stamp = str(row["ETF代號"]).strip(), source_date(row["恢復買賣日期"])
        if not start <= stamp <= end or (symbol, stamp) in seen:
            raise ValueError("official split row outside requested dates or duplicated")
        seen.add((symbol, stamp))
        upper, lower = number(row["漲停價格"]), number(row["跌停價格"])
        events.append({"symbol": symbol, "date": stamp.isoformat(), "kind": str(row["分割(反分割)"]).strip(),
                       "prior_close": float(number(row["停止買賣前收盤價格"])),
                       "reference_price": float(number(row["恢復買賣參考價"])),
                       "upper_limit": float(upper), "lower_limit": float(lower),
                       "no_limit": upper >= NO_LIMIT_UPPER and lower <= NO_LIMIT_LOWER})
    return sorted(events, key=lambda event: (event["date"], event["symbol"]))


def derive_ratio(prior, reference):
    """官方公式：恢復買賣參考價 = 前收盤 ÷ 分割比率（反分割為相乘），誤差在一檔內；僅整數比率且唯一解才採用。"""
    found = [Decimal(n) for n in range(2, 101) if abs(prior / n - reference) <= TICK]
    found += [Decimal(1) / n for n in range(2, 101) if abs(prior * n - reference) <= TICK]
    return found[0] if len(found) == 1 else None


def page_text(content):
    text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.DOTALL)
    return html.unescape(re.sub(r"<[^>]+>", "\n", text))


def parse_split_announcement(content):
    text = page_text(content)

    def find(pattern):
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"announcement field missing: {pattern}")
        return match[1]

    return {"symbol": find(r"證券代碼\s*([0-9]{4,6}[A-Z]?)"),
            "ratio": number(find(r"分割比率[^：:\n]*[：:]\s*([0-9]+(?:\.[0-9]+)?)")),
            "last_trading_day": source_date(find(r"最後交易日期[：:]\s*(\d+年\d+月\d+日)")).isoformat(),
            "resume_day": source_date(find(r"上市\(櫃\)買賣日[：:]\s*(\d+年\d+月\d+日)")).isoformat(),
            "reference_price": number(find(r"參考價\(即恢復買賣參考價\)為\s*([0-9.]+)元")),
            "prior_close": number(find(r"之收盤價\(([0-9.,]+)元\)"))}


def reconcile_announcement(event, announced):
    prior, reference = Decimal(str(event["prior_close"])), Decimal(str(event["reference_price"]))
    if (announced["symbol"] != event["symbol"] or announced["resume_day"] != event["date"]
            or announced["reference_price"] != reference or announced["prior_close"] != prior
            or derive_ratio(prior, reference) != announced["ratio"]):
        raise ValueError("issuer announcement disagrees with the official split table")
    return announced["ratio"]


def collect_splits(output, symbols, start, end, announcements=None, session=None):
    validate_symbols(symbols)
    start, end = source_date(start), source_date(end)
    if start > end:
        raise ValueError("ordered date range required")
    announcements = announcements or {}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    observed = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    save_new(output / "started.json", {"observed_at": observed, "start": start.isoformat(), "end": end.isoformat(), "symbols": symbols})
    session = requests.Session() if session is None else session
    artifacts = []

    def fetch(url, name, params=None):
        reply = session.get(url, params=params, timeout=60, headers={"User-Agent": "tw-stock-analysis/research-source-check"})
        reply.raise_for_status()
        path = raw / name
        with path.open("xb") as stream:
            stream.write(reply.content)
        artifacts.append({"path": path.relative_to(output).as_posix(), "sha256": file_hash(path), "url": url,
                          "params": params, "observed_at": observed})
        return reply.content

    try:
        params = {"response": "json", "startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d")}
        events = parse_split_table(json.loads(fetch(SPLIT, "twtcau.json", params).decode("utf-8-sig")), start, end)
        actions, unresolved, confirmed = [], [], 0
        for event in (event for event in events if event["symbol"] in symbols):
            prior, reference = Decimal(str(event["prior_close"])), Decimal(str(event["reference_price"]))
            ratio, basis = derive_ratio(prior, reference), "official_reference_price_formula"
            try:
                if event["symbol"] in announcements:
                    page = fetch(announcements[event["symbol"]], f"announcement_{event['symbol']}.html")
                    ratio, basis = reconcile_announcement(event, parse_split_announcement(page)), "issuer_announcement_confirmed"
                    confirmed += 1
                elif ratio is None:
                    raise ValueError("no unique integer ratio satisfies the official reference-price formula")
            except ValueError as exc:
                unresolved.append({**event, "reason": str(exc)})
                continue
            actions.append({"symbol": event["symbol"], "date": event["date"], "cash_dividend": 0.0, "share_ratio": float(ratio),
                            "source": "TWSE_TWTCAU", "basis": basis, "prior_close": event["prior_close"],
                            "reference_price": event["reference_price"], "kind": event["kind"]})
        evidence = {"actions": actions, "coverage": [], "membership": [], "listing_facts": [], "tradability": []}
        save_new(output / "evidence.json", evidence)
        save_new(output / "unresolved.json", unresolved)
        save_new(output / "manifest.json", {
            "certified_complete": False, "artifacts": artifacts, "symbols": symbols, "start": start.isoformat(),
            "end": end.isoformat(), "observed_at": observed,
            "earliest_table_event": events[0]["date"] if events else None, "table_events": len(events),
            "limitations": ["官方分割表只列恢復買賣事件，最早事件之前不證明沒有分割。",
                            "比率依官方公式在唯一整數解下推得；有發行人公告者另行逐項核對。",
                            "分割日現金股利記 0，不證明當日無其他權利；與除息表重疊時需明確合併。",
                            "不含無事件日的零值覆蓋，需另行證明完整覆蓋。"]})
        result = {"status": "partial_evidence" if actions else "no_data", "certified_complete": False, "actions": len(actions),
                  "unresolved": len(unresolved), "announcement_confirmed": confirmed, "output": str(output)}
        save_new(output / "result.json", result)
        return result
    except (requests.RequestException, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        save_new(output / "failure.json", {"error": str(exc), "artifacts": artifacts, "certified_complete": False})
        raise
