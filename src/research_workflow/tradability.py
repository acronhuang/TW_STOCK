import json
import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

import requests

from .data import validate_symbols
from .registry import file_hash, save_new
from .sources import EXRIGHT, number, source_date
from .splits import SPLIT, parse_split_table

HALTS = "https://www.twse.com.tw/rwd/zh/afterTrading/TWTAWU"
DAILY = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
RESCUABLE = {"no_prior_row", "prior_close_not_corroborated", "observed_price_outside_derived_limits"}
ETF = re.compile(r"00[0-9]{2,4}[LRU]?")
ORDINARY = re.compile(r"00[0-9]{2,4}")
LIMIT_CUTOVER = date(2015, 6, 1)
HALT_HISTORY_START = date(2011, 10, 3)
SOURCE = "derived_price_limit"
NO_LIMIT_UPPER, NO_LIMIT_LOWER = Decimal("9999.95"), Decimal("0.01")


def tick(price):
    return Decimal("0.01") if price < 50 else Decimal("0.05")


def limit_prices(base, day):
    pct = Decimal("0.07") if day < LIMIT_CUTOVER else Decimal("0.10")
    upper, lower = base * (1 + pct), base * (1 - pct)
    upper_step, lower_step = tick(upper), tick(lower)
    return ((upper / upper_step).to_integral_value(ROUND_FLOOR) * upper_step,
            (lower / lower_step).to_integral_value(ROUND_CEILING) * lower_step)


def parse_exright_limits(payload, start, end):
    start, end = source_date(start), source_date(end)
    if payload.get("stat") != "OK":
        raise ValueError("official query did not return OK")
    if str(payload.get("strDate")) != start.strftime("%Y%m%d") or str(payload.get("endDate")) != end.strftime("%Y%m%d"):
        raise ValueError("official response date range does not match request")
    fields = payload.get("fields", [])
    required = {"資料日期", "股票代號", "除權息參考價", "漲停價格", "跌停價格"}
    if not required.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official exright schema changed")
    events, seen = [], set()
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol = str(row["股票代號"]).strip()
        if ETF.fullmatch(symbol) is None:
            continue
        stamp = source_date(row["資料日期"])
        if not start <= stamp <= end or (symbol, stamp) in seen:
            raise ValueError("official row outside requested dates or duplicated")
        seen.add((symbol, stamp))
        upper, lower = number(row["漲停價格"]), number(row["跌停價格"])
        events.append({"symbol": symbol, "date": stamp.isoformat(), "reference_price": float(number(row["除權息參考價"])),
                       "upper_limit": float(upper), "lower_limit": float(lower),
                       "no_limit": upper >= NO_LIMIT_UPPER and lower <= NO_LIMIT_LOWER})
    return sorted(events, key=lambda event: (event["date"], event["symbol"]))


def verify_limits(events):
    mismatches, checked, unvalidated = [], 0, 0
    for event in events:
        if ORDINARY.fullmatch(event["symbol"]) is None:
            unvalidated += 1
            continue
        if event["no_limit"]:
            continue
        checked += 1
        upper, lower = limit_prices(Decimal(str(event["reference_price"])), date.fromisoformat(event["date"]))
        if upper != Decimal(str(event["upper_limit"])) or lower != Decimal(str(event["lower_limit"])):
            mismatches.append({**event, "derived_upper": float(upper), "derived_lower": float(lower)})
    return {"events": checked, "mismatches": mismatches, "unvalidated_class_events": unvalidated,
            "no_limit_events": len(events) - checked - unvalidated}


def clock(day, text):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(text).strip())
    if match is None:
        raise ValueError("unrecognized halt time")
    return datetime.combine(day, time(int(match[1]), int(match[2])))


def parse_halts(payload, symbols, start, end):
    start, end = source_date(start), source_date(end)
    if payload.get("stat") != "OK":
        raise ValueError("official halt query did not return OK")
    period = re.search(r"期間：(\S+) 到 (\S+)", str(payload.get("title")))
    if period is None or (source_date(period[1]), source_date(period[2])) != (start, end):
        raise ValueError("official halt period does not match request")
    fields = payload.get("fields", [])
    required = {"證券代號", "暫停交易日期", "暫停交易時間", "恢復交易日期", "恢復交易時間"}
    if not required.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official halt schema changed")
    result = []
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official halt row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol = str(row["證券代號"]).strip()
        if symbol not in symbols:
            continue
        resume = (clock(source_date(row["恢復交易日期"]), row["恢復交易時間"]).isoformat()
                  if str(row["恢復交易日期"]).strip() else None)
        result.append({"symbol": symbol, "start": clock(source_date(row["暫停交易日期"]), row["暫停交易時間"]).isoformat(),
                       "resume": resume})
    return result


def halted(stops, day):
    opens, closes = datetime.combine(day, time(9, 0)), datetime.combine(day, time(13, 30))
    return any(datetime.fromisoformat(stop["start"]) < closes
               and (stop["resume"] is None or datetime.fromisoformat(stop["resume"]) > opens) for stop in stops)


def parse_daily_table(payload, symbol, month):
    stat = str(payload.get("stat"))
    if stat != "OK":
        if "沒有符合條件" in stat:
            return []
        raise ValueError("official daily table did not return OK")
    if symbol not in str(payload.get("title")):
        raise ValueError("official daily table is for another security")
    fields = payload.get("fields", [])
    required = {"日期", "開盤價", "最高價", "最低價", "收盤價"}
    if not required.issubset(fields) or len(set(fields)) != len(fields) or not isinstance(payload.get("data"), list):
        raise ValueError("official daily table schema changed")
    rows = []
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official daily row does not match schema")
        row = dict(zip(fields, values, strict=True))
        stamp = source_date(row["日期"])
        if (stamp.year, stamp.month) != tuple(month):
            raise ValueError("official daily row outside requested month")
        try:
            prices = [number(row[name]) for name in ("開盤價", "最高價", "最低價", "收盤價")]
        except ValueError:
            continue
        if min(prices) > 0:
            rows.append({"date": stamp.isoformat(), "open": prices[0], "high": prices[1], "low": prices[2], "close": prices[3]})
    return rows


def previous_official_close(table, day):
    earlier = [posted for posted in table["days"] if posted < day.isoformat()]
    if not earlier:
        return None
    last = date.fromisoformat(max(earlier))
    year, month = last.year, last.month
    while (year, month) <= (day.year, day.month):
        if (year, month) not in table["months"]:
            return None
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return table["days"][last.isoformat()]["close"]


def derive_tradability(rows, references, stops, start, calendar=None, official=None):
    start = source_date(start)
    official = official or {}
    position = None if calendar is None else {stamp: index for index, stamp in enumerate(sorted(calendar))}
    series = {}
    for row in rows:
        series.setdefault(str(row["symbol"]), []).append(row)
    entries, withheld = [], []
    for symbol, items in sorted(series.items()):
        items.sort(key=lambda row: source_date(row["date"]))
        own_stops = [stop for stop in stops if stop["symbol"] == symbol]
        for index, row in enumerate(items):
            day = source_date(row["date"])
            if day < start:
                continue
            stamp = day.isoformat()

            def hold(reason, symbol=symbol, stamp=stamp):
                withheld.append({"symbol": symbol, "date": stamp, "reason": reason})

            if ETF.fullmatch(symbol) is None:
                hold("unsupported_instrument")
                continue
            try:
                opened, high, low, close, volume = (number(row[name]) for name in ("open", "high", "low", "close", "volume"))
            except (ValueError, TypeError, KeyError):
                hold("no_trade_or_invalid_price")
                continue
            if min(opened, high, low, close) <= 0 or volume <= 0:
                hold("no_trade_or_invalid_price")
                continue
            if position is not None and stamp not in position:
                hold("date_not_in_trading_calendar")
                continue
            reference = references.get((symbol, stamp))
            if (symbol, stamp) in references and reference is None:
                hold("official_no_price_limit")
                continue
            limits = None
            base = basis = None
            if reference is not None:
                if isinstance(reference, tuple):
                    base, basis = Decimal(str(reference[0])), "official_split_resumption_limits"
                    limits = (Decimal(str(reference[1])), Decimal(str(reference[2])))
                else:
                    base, basis = Decimal(str(reference)), "official_reference_price"
            else:
                table = official.get(symbol)
                posted = table["days"].get(stamp) if table else None
                if posted is not None:
                    if (opened, high, low, close) != (posted["open"], posted["high"], posted["low"], posted["close"]):
                        hold("official_daily_mismatch")
                        continue
                    prior_close = previous_official_close(table, day)
                    if prior_close is not None:
                        base, basis = prior_close, "prior_close_official_daily_table"
            if base is None:
                if index == 0:
                    hold("no_prior_row")
                    continue
                try:
                    prior = number(items[index - 1]["close"])
                    change = None if row.get("spread") is None else number(row["spread"])
                except (ValueError, TypeError, KeyError):
                    hold("prior_close_not_corroborated")
                    continue
                if change is not None:
                    if abs(prior - (close - change)) > Decimal("0.005"):
                        hold("prior_close_not_corroborated")
                        continue
                    base, basis = prior, "prior_close_corroborated_by_spread"
                else:
                    before = source_date(items[index - 1]["date"]).isoformat()
                    if position is None or before not in position or position[before] + 1 != position[stamp]:
                        hold("prior_close_not_corroborated")
                        continue
                    base, basis = prior, "prior_close_adjacent_trading_day"
            if halted(own_stops, day):
                hold("official_halt_overlaps_session")
                continue
            upper, lower = limits or limit_prices(base, day)
            if limits is None and ORDINARY.fullmatch(symbol) is None:
                if not lower < opened < upper:
                    hold("possible_limit_lock_unverified")
                    continue
                rule = "minimum_band_only"
            else:
                if high > upper or low < lower or opened > upper or opened < lower:
                    hold("observed_price_outside_derived_limits")
                    continue
                rule = "official_limits" if limits else "validated_ordinary"
            entries.append({"symbol": symbol, "date": stamp, "can_buy": opened < upper, "can_sell": opened > lower,
                            "available_at": f"{stamp}T00:00:00", "source": SOURCE, "basis": basis,
                            "base_price": float(base), "upper_limit": float(upper), "lower_limit": float(lower),
                            "limit_rule": rule})
    return {"tradability": entries, "withheld": withheld}


def collect_tradability(output, symbols, start, end, session=None, db=None, pause=1.5):
    validate_symbols(symbols)
    if any(ETF.fullmatch(symbol) is None for symbol in symbols):
        raise ValueError("verified ETF symbols only; stock and bond-ETF limit rules do not reproduce the official table")
    start, end = source_date(start), source_date(end)
    if start > end or start < HALT_HISTORY_START or end.year - start.year >= 20:
        raise ValueError("ordered date range within official halt history and twenty calendar years required")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    observed = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    save_new(output / "started.json", {"observed_at": observed, "start": start.isoformat(), "end": end.isoformat(), "symbols": symbols})
    session = requests.Session() if session is None else session
    artifacts = []

    def fetch(url, params, name):
        reply = session.get(url, params=params, timeout=60, headers={"User-Agent": "tw-stock-analysis/research-source-check"})
        reply.raise_for_status()
        path = raw / name
        with path.open("xb") as stream:
            stream.write(reply.content)
        artifacts.append({"path": path.relative_to(output).as_posix(), "sha256": file_hash(path),
                          "url": url, "params": params, "observed_at": observed})
        return json.loads(reply.content.decode("utf-8-sig"))

    try:
        events = []
        for year in range(start.year, end.year + 1):
            first, last = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
            params = {"startDate": first.strftime("%Y%m%d"), "endDate": last.strftime("%Y%m%d"), "response": "json"}
            events.extend(parse_exright_limits(fetch(EXRIGHT, params, f"exright_{year}.json"), first, last))
        check = verify_limits(events)
        if not check["events"]:
            raise ValueError("no official limit events to validate the derived rule")
        if check["mismatches"]:
            raise ValueError(f"derived limits disagree with official limit table: {check['mismatches'][:3]}")
        params = {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "response": "json"}
        stops = parse_halts(fetch(HALTS, params, "halts.json"), symbols, start, end)
        if db is None:
            from src.config import get_db

            db = get_db()
        fields = {"_id": 0, **{name: 1 for name in ("date", "symbol", "open", "high", "low", "close", "spread", "volume")}}
        query = {"symbol": {"$in": symbols},
                 "date": {"$gte": datetime.combine(start - timedelta(days=15), time.min), "$lte": datetime.combine(end, time.max)}}
        rows = list(db["stock_price"].find(query, fields))
        native = raw / "stock_price.json"
        save_new(native, json.loads(json.dumps(rows, default=str, allow_nan=False)))
        artifacts.append({"path": native.relative_to(output).as_posix(), "sha256": file_hash(native),
                          "source": "MongoDB.stock_price", "observed_at": observed})
        references = {(event["symbol"], event["date"]): None if event["no_limit"] else event["reference_price"]
                      for event in events if event["symbol"] in symbols}
        split_params = {"response": "json", "startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d")}
        splits = [event for event in parse_split_table(fetch(SPLIT, split_params, "twtcau.json"), start, end)
                  if event["symbol"] in symbols]
        for event in splits:
            references[(event["symbol"], event["date"])] = (
                None if event["no_limit"] else (event["reference_price"], event["upper_limit"], event["lower_limit"]))
        days = [str(row["date"]) for row in db["trading_dates"].find({}, {"_id": 0, "date": 1})]
        if not days:
            raise ValueError("trading calendar required to corroborate prior closes")
        calendar = native.with_name("trading_dates.json")
        save_new(calendar, sorted(days))
        artifacts.append({"path": calendar.relative_to(output).as_posix(), "sha256": file_hash(calendar),
                          "source": "MongoDB.trading_dates", "observed_at": observed})
        calendar_days = [source_date(day).isoformat() for day in days]
        derived = derive_tradability(rows, references, stops, start, calendar_days)
        wanted = set()
        for item in derived["withheld"]:
            if item["reason"] in RESCUABLE:
                year, month = int(item["date"][:4]), int(item["date"][5:7])
                wanted |= {(item["symbol"], year, month), (item["symbol"], year - (month == 1), month - 1 or 12)}
        official, failures, fetched_months = {}, [], 0
        for symbol, year, month in sorted(wanted):
            payload = None
            for _ in range(2):
                try:
                    payload = fetch(DAILY, {"date": f"{year}{month:02d}01", "stockNo": symbol, "response": "json"},
                                    f"stock_day_{symbol}_{year}{month:02d}.json")
                    break
                except requests.RequestException:
                    sleep(pause)
                except ValueError:
                    break
            sleep(pause)
            try:
                table = parse_daily_table(payload, symbol, (year, month)) if payload is not None else None
            except ValueError:
                table = None
            if table is None:
                failures.append({"symbol": symbol, "month": f"{year}{month:02d}"})
                continue
            fetched_months += bool(table)
            kept = official.setdefault(symbol, {"days": {}, "months": set()})
            kept["months"].add((year, month))
            kept["days"].update({row["date"]: row for row in table})
        failed_keys = {(item["symbol"], item["date"]) for item in derived["withheld"]}
        if official:
            derived = derive_tradability(rows, references, stops, start, calendar_days, official)
        rescued = sum((item["symbol"], item["date"]) in failed_keys and item["basis"] == "prior_close_official_daily_table"
                      for item in derived["tradability"])
        evidence = {"actions": [], "coverage": [], "membership": [], "listing_facts": [], "tradability": derived["tradability"]}
        save_new(output / "evidence.json", evidence)
        save_new(output / "withheld.json", derived["withheld"])
        reasons = {}
        for item in derived["withheld"]:
            reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
        save_new(output / "manifest.json", {
            "certified_complete": False, "artifacts": artifacts, "symbols": symbols,
            "start": start.isoformat(), "end": end.isoformat(), "observed_at": observed,
            "validation": {"official_limit_events": check["events"], "official_no_limit_events": check["no_limit_events"],
                           "mismatches": 0, "withheld_reasons": reasons, "split_events": len(splits), "unvalidated_class_events": check["unvalidated_class_events"],
                           "official_daily_months": fetched_months, "official_daily_failures": failures,
                           "rescued_by_official_daily": rescued},
            "limitations": ["僅限 ETF；個股與債券型 ETF 的漲跌停規則無法由此規則重現官方表。",
                            "開盤價等於漲跌停價時保守視為該方向不可成交；未涵蓋其他個別交易限制。",
                            "由前收盤與官方規則推導，不是交易所逐日公告的可交易旗標。",
                            "官方日成交表只用於保留列；其價格與資料庫不同時該列改為保留。",
                            "分割恢復買賣首日採官方公布漲跌停價，不以十分之一規則推導。",
                            "不提供上市日、股票池、公司行動或股數權利證據。"]})
        result = {"status": "partial_evidence" if derived["tradability"] else "no_data", "certified_complete": False,
                  "tradability": len(derived["tradability"]), "withheld": len(derived["withheld"]),
                  "official_limit_events": check["events"], "output": str(output)}
        save_new(output / "result.json", result)
        return result
    except (requests.RequestException, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        save_new(output / "failure.json", {"error": str(exc), "artifacts": artifacts, "certified_complete": False})
        raise
