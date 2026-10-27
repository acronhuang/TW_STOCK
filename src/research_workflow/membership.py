import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .data import validate_symbols
from .persistence import load_snapshot
from .registry import file_hash, save_new
from .sources import ISIN, parse_isin, source_date

STOCK = re.compile(r"[1-9][0-9]{3}")
ETF = re.compile(r"00[0-9]{2,4}[A-Z]?")
SOURCE = "derived_listing_status"
RULE = ("eligible = 上市日 <= 日期 < 下市日，且代號屬已登記標的（4 碼普通股、00 開頭 ETF）；"
        "不含流動性、產業或股票池成分判斷，流動性與上市根數另由 signal_universe 處理。")


def instrument_allowed(symbol):
    return STOCK.fullmatch(symbol) is not None or ETF.fullmatch(symbol) is not None


def build_membership(symbols, start, end, listings, first_prices, delistings, observed_on):
    start, end = source_date(start), source_date(end)
    stops = {}
    for fact in delistings:
        stops.setdefault(fact["symbol"], set()).add(source_date(fact["delisted_on"]))
    rows, unresolved, basis_counts = [], [], {}
    for symbol in sorted(symbols):
        if len(stops.get(symbol, ())) > 1:
            unresolved.append({"symbol": symbol, "reason": "multiple_delisting_facts"})
            continue
        if listings.get(symbol) is not None:
            listed, basis = listings[symbol], "isin_listing_date"
        elif first_prices.get(symbol) is not None:
            listed, basis = first_prices[symbol], "first_observed_price_lower_bound"
        else:
            unresolved.append({"symbol": symbol, "reason": "listing_date_unavailable"})
            continue
        delisted = min(stops[symbol]) if symbol in stops else None
        if delisted is not None and delisted <= listed:
            unresolved.append({"symbol": symbol, "reason": "delisting_not_after_listing"})
            continue
        basis_counts[basis] = basis_counts.get(basis, 0) + 1
        allowed = instrument_allowed(symbol)

        def span(first, last, eligible, reason, symbol=symbol, listed=listed, basis=basis):
            if first <= last:
                rows.append({"symbol": symbol, "start": first.isoformat(), "end": last.isoformat(),
                             "available_at": f"{first.isoformat()}T00:00:00", "eligible": eligible,
                             "listed_on": listed.isoformat(), "source": SOURCE, "basis": basis, "reason": reason,
                             "observed_on": observed_on})

        one_day = timedelta(days=1)
        span(start, min(end, listed - one_day), False, "before_listing")
        span(max(start, listed), end if delisted is None else min(end, delisted - one_day), allowed,
             "listed" if allowed else "instrument_not_in_registered_universe")
        if delisted is not None:
            span(max(start, delisted), end, False, "delisted")
    return {"membership": rows, "unresolved": unresolved, "basis_counts": dict(sorted(basis_counts.items()))}


def collect_membership(output, symbols, start, end, snapshot_id, session=None, db=None):
    validate_symbols(symbols)
    start, end = source_date(start), source_date(end)
    if start > end:
        raise ValueError("ordered date range required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    observed = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    save_new(output / "started.json", {"observed_at": observed, "start": start.isoformat(), "end": end.isoformat(), "symbols": symbols})
    session = requests.Session() if session is None else session
    artifacts = []

    def archive(name, content, **meta):
        path = raw / name
        with path.open("xb") as stream:
            stream.write(content)
        artifacts.append({"path": path.relative_to(output).as_posix(), "sha256": file_hash(path), "observed_at": observed, **meta})

    try:
        listings, conflicts = {}, []
        for mode, name in (("2", "isin_twse.html"), ("4", "isin_tpex.html")):
            reply = session.get(ISIN, params={"strMode": mode}, timeout=60,
                                headers={"User-Agent": "tw-stock-analysis/research-source-check"})
            reply.raise_for_status()
            archive(name, reply.content, url=ISIN, params={"strMode": mode})
            try:
                html = reply.content.decode("cp950")
            except UnicodeDecodeError:
                html = reply.content.decode("utf-8-sig")
            for fact in parse_isin(html, symbols, observed)["listing_facts"]:
                if fact["symbol"] in listings:
                    conflicts.append(fact["symbol"])
                listings[fact["symbol"]] = source_date(fact["listed_on"])
        if db is None:
            from src.config import get_db

            db = get_db()
        first = {row["_id"]: row["first"].date() for row in db["stock_price"].aggregate(
            [{"$match": {"symbol": {"$in": symbols}}}, {"$group": {"_id": "$symbol", "first": {"$min": "$date"}}}])}
        native = raw / "first_prices.json"
        save_new(native, {symbol: day.isoformat() for symbol, day in sorted(first.items())})
        artifacts.append({"path": native.relative_to(output).as_posix(), "sha256": file_hash(native),
                          "source": "MongoDB.stock_price", "observed_at": observed})
        delistings = load_snapshot(snapshot_id, symbols, start.isoformat(), end.isoformat(), db)["delisting_facts"]
        conflicted = sorted(set(conflicts))
        built = build_membership([symbol for symbol in symbols if symbol not in conflicted], start, end, listings, first,
                                 delistings, observed)
        unresolved = [{"symbol": symbol, "reason": "listed_on_both_markets"} for symbol in conflicted] + built["unresolved"]
        evidence = {"actions": [], "coverage": [], "listing_facts": [], "tradability": [], "membership": built["membership"]}
        save_new(output / "evidence.json", evidence)
        save_new(output / "unresolved.json", unresolved)
        save_new(output / "manifest.json", {
            "certified_complete": False, "artifacts": artifacts, "symbols": symbols, "start": start.isoformat(),
            "end": end.isoformat(), "observed_at": observed, "snapshot_id": snapshot_id,
            "eligibility_rule": RULE, "basis_counts": built["basis_counts"],
            "limitations": ["ISIN 只含目前仍上市者的上市日；已下市或無 ISIN 者以首筆價格日作上市日下界。",
                            "下市日來自既有來源快照，不等於完整下市結算或歷史股票池。",
                            "轉上市／上櫃者，上市日為現市場掛牌日；更早的他市場列判為不合格（保守）。",
                            "標的類型只依代號格式判斷；不含產業、流動性或成分股資格。"]})
        result = {"status": "partial_evidence" if built["membership"] else "no_data", "certified_complete": False,
                  "membership": len(built["membership"]), "unresolved": len(unresolved), "output": str(output)}
        save_new(output / "result.json", result)
        return result
    except (requests.RequestException, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        save_new(output / "failure.json", {"error": str(exc), "artifacts": artifacts, "certified_complete": False})
        raise
