import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .data import validate_symbols
from .registry import digest, file_hash, save_new

EXRIGHT = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
ISIN = "https://isin.twse.com.tw/isin/C_public.jsp"
CASH_TOLERANCE = Decimal("0.0001")


def import_finmind(output, receipts, start, end):
    start, end = source_date(start), source_date(end)
    if start > end:
        raise ValueError("ordered date range required")
    output, receipts = Path(output), Path(receipts)
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    summary_path = receipts / "result.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    observed = datetime.fromisoformat(summary["captured_at"])
    if observed.utcoffset() is None:
        raise ValueError("capture timestamp requires timezone")
    datasets = ("TaiwanStockDelisting", "TaiwanStockSplitPrice", "TaiwanStockParValueChange")
    checks = summary["checks"]
    if len(checks) != len(datasets) or {check["dataset"] for check in checks} != set(datasets):
        raise ValueError("exactly three supplier receipts required")
    artifacts = []
    with (raw / "supplier_result.json").open("xb") as stream:
        stream.write(summary_path.read_bytes())
    artifacts.append({"path": "raw/supplier_result.json", "sha256": file_hash(raw / "supplier_result.json")})
    evidence = {"actions": [], "coverage": [], "membership": [], "tradability": [], "unresolved": [],
                "delisting_facts": [], "reference_events": []}
    references = {}
    price_fields = ("before_price", "after_price", "max_price", "min_price", "open_price")
    par_fields = ("before_close", "after_ref_close", "after_ref_max", "after_ref_min", "after_ref_open")
    for check in checks:
        dataset = check["dataset"]
        content = (receipts / f"{dataset}.response.json").read_bytes()
        target = raw / f"{dataset}.response.json"
        with target.open("xb") as stream:
            stream.write(content)
        checksum = file_hash(target)
        if checksum != check["raw_sha256"]:
            raise ValueError("supplier receipt hash mismatch")
        body = json.loads(content)
        if (check.get("http_status") != 200 or body.get("status") != 200
                or check.get("request") != {"dataset": dataset} or not isinstance(body.get("data"), list)):
            raise ValueError("supplier receipt is not a successful unfiltered query")
        if len(body["data"]) != check.get("rows"):
            raise ValueError("supplier receipt row count mismatch")
        artifacts.append({"path": str(target.relative_to(output)), "sha256": checksum,
                          "dataset": dataset, "observed_at": observed.isoformat()})
        seen = set()
        for row in body["data"]:
            fields = ({"date", "stock_id", "stock_name"} if dataset == datasets[0] else
                      {"date", "stock_id", "type", *price_fields} if dataset == datasets[1] else
                      {"date", "stock_id", "stock_name", *par_fields})
            if not isinstance(row, dict) or not fields.issubset(row):
                raise ValueError("supplier event schema changed")
            symbol = row["stock_id"]
            validate_symbols([symbol])
            stamp = date.fromisoformat(row["date"])
            key = (symbol, stamp)
            if key in seen:
                raise ValueError("duplicate supplier event")
            seen.add(key)
            if dataset == datasets[0]:
                if start <= stamp <= end:
                    evidence["delisting_facts"].append({"symbol": symbol, "delisted_on": stamp.isoformat(),
                                                        "source": dataset, "observed_at": observed.isoformat()})
                continue
            native_fields = price_fields if dataset == datasets[1] else par_fields
            prices = {field: float(number(row[native])) for field, native in zip(price_fields, native_fields, strict=True)}
            if any(value <= 0 for value in prices.values()):
                raise ValueError("supplier reference prices must be positive")
            kind = row["type"] if dataset == datasets[1] else "面額變更"
            if kind not in {"", "分割", "反分割", "面額變更"}:
                raise ValueError("unknown supplier reference event kind")
            if not start <= stamp <= end:
                continue
            event = {"symbol": symbol, "date": stamp.isoformat(), "kind": kind, **prices}
            if kind == "":
                evidence["unresolved"].append({**event, "source": dataset, "reason": "Missing supplier event type."})
                continue
            if key in references:
                if {name: value for name, value in references[key].items() if name != "sources"} != event:
                    raise ValueError("conflicting supplier reference events")
                references[key]["sources"] = sorted([*references[key]["sources"], dataset])
            else:
                references[key] = {**event, "sources": [dataset]}
    evidence["reference_events"] = [references[key] for key in sorted(references)]
    evidence["delisting_facts"].sort(key=lambda row: (row["symbol"], row["delisted_on"]))
    save_new(output / "evidence.json", evidence)
    save_new(output / "manifest.json", {"artifacts": artifacts, "certified_complete": False,
             "start": start.isoformat(), "end": end.isoformat(), "observed_at": observed.isoformat(),
             "limitations": ["Delisting observations are not complete historical membership or settlement evidence.",
                             "Reference prices do not establish share entitlements or payment dates.",
                             "Empty responses and observed date ranges do not certify complete coverage.",
                             "Capture time is not historical announcement availability."]})
    count = len(references) + len(evidence["delisting_facts"]) + len(evidence["unresolved"])
    result = {"status": "partial_evidence" if count else "no_data", "certified_complete": False,
              "delisting_facts": len(evidence["delisting_facts"]), "reference_events": len(references),
              "unresolved": len(evidence["unresolved"]), "output": str(output)}
    save_new(output / "result.json", result)
    return result


def source_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        match = re.fullmatch(r"(\d{2,4})(?:年|/|-)(\d{1,2})(?:月|/|-)(\d{1,2})日?", raw)
        if match is None:
            raise ValueError(f"unrecognized source date: {raw}") from None
        year, month, day = (int(part) for part in match.groups())
        return date(year + 1911 if year < 1911 else year, month, day)


def number(value):
    if hasattr(value, "to_decimal"):
        value = value.to_decimal()
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError("missing or invalid source amount") from None
    if not result.is_finite():
        raise ValueError("nonfinite source amount")
    return result


def parse_exright(payload, symbols, start, end):
    start, end = source_date(start), source_date(end)
    if payload.get("stat") != "OK":
        raise ValueError("official query did not return OK; absence is not proof of no events")
    if str(payload.get("strDate")) != start.strftime("%Y%m%d") or str(payload.get("endDate")) != end.strftime("%Y%m%d"):
        raise ValueError("official response date range does not match request")
    fields = payload.get("fields", [])
    required = {"資料日期", "股票代號", "權值+息值", "權/息", "漲停價格", "跌停價格"}
    if not required.issubset(fields) or len(set(fields)) != len(fields):
        raise ValueError("official exright schema changed")
    if not isinstance(payload.get("data"), list):
        raise TypeError("missing official data array")
    events, unresolved, seen = [], [], set()
    for values in payload["data"]:
        if len(values) != len(fields):
            raise ValueError("official row does not match schema")
        row = dict(zip(fields, values, strict=True))
        symbol = str(row["股票代號"]).strip()
        if symbol not in symbols:
            continue
        stamp = source_date(row["資料日期"])
        if not start <= stamp <= end:
            raise ValueError("official row outside requested dates")
        key = (symbol, stamp)
        if key in seen:
            raise ValueError("duplicate official event")
        seen.add(key)
        event = {"symbol": symbol, "date": stamp.isoformat(), "kind": str(row["權/息"]).strip(),
                 "source": "TWSE_TWT49U", "upper_limit": float(number(row["漲停價格"])),
                 "lower_limit": float(number(row["跌停價格"]))}
        if event["kind"] != "息":
            unresolved.append({**event, "reason": "股數權利或認購條件需另取明細，不從價格差推定。"})
            continue
        amount = number(row["權值+息值"])
        if amount <= 0:
            raise ValueError("invalid official cash dividend")
        events.append({**event, "cash_amount": float(amount)})
    return {"events": events, "unresolved": unresolved, "coverage": []}


def reconcile_cash(events, dividend_rows):
    actions, unresolved = [], []
    for event in events:
        matches = []
        invalid = False
        for row in dividend_rows:
            if str(row.get("stock_id")) != event["symbol"] or not row.get("cash_ex_dividend_date"):
                continue
            try:
                if source_date(row["cash_ex_dividend_date"]).isoformat() != event["date"]:
                    continue
                cash = number(row.get("cash_earnings_distribution")) + number(row.get("cash_statutory_surplus"))
                payment = source_date(row.get("cash_dividend_payment_date"))
                if abs(cash - number(event["cash_amount"])) > CASH_TOLERANCE or payment < source_date(event["date"]):
                    invalid = True
                    continue
                matches.append((cash, payment))
            except (ValueError, TypeError):
                invalid = True
        unique = set(matches)
        if invalid or len(unique) != 1:
            unresolved.append({**event, "reason": "缺少一致的股息金額及實際發放日，或來源相互衝突。"})
            continue
        cash, payment = unique.pop()
        actions.append({"symbol": event["symbol"], "date": event["date"], "cash_dividend": float(cash),
                        "cash_payment_date": payment.isoformat(), "share_ratio": 1.0,
                        "source": "TWSE_TWT49U+FinMind.dividend_detail",
                        "official_cash_amount": event["cash_amount"],
                        "payment_date_source": "FinMind.dividend_detail",
                        "cash_match_tolerance": float(CASH_TOLERANCE)})
    return {"actions": actions, "unresolved": unresolved, "coverage": []}


def reconcile_tsmc_capture(events, capture):
    issuer = "https://investor.tsmc.com/english/dividends"
    if capture.get("url") != issuer or capture.get("capture_method") != "integrated_browser_rendered_DOM":
        raise ValueError("official issuer browser capture required")
    datetime.fromisoformat(capture["captured_at"])
    tables = [table for table in capture["tables"] if table.get("headers") and "Per Common Share" in table["headers"][0]]
    if len(tables) != 1:
        raise ValueError("exactly one issuer common-share table required")
    table = tables[0]
    fields = table["headers"][0]
    required = {"Per Common Share", "Cash Dividend", "Ex-Dividend Date", "Distribution Date"}
    if not required.issubset(fields) or len(fields) != len(set(fields)):
        raise ValueError("issuer dividend schema changed")
    rows = {}
    for values in table["rows"]:
        if len(values) != len(fields):
            raise ValueError("issuer row does not match schema")
        row = dict(zip(fields, values, strict=True))
        if row["Per Common Share"] != "-" or not row["Cash Dividend"].startswith("NT$"):
            raise ValueError("issuer capture must contain cash-only common-share TWD dividends")
        stamp = source_date(row["Ex-Dividend Date"]).isoformat()
        if stamp in rows:
            raise ValueError("duplicate issuer dividend date")
        rows[stamp] = (number(row["Cash Dividend"][3:]), source_date(row["Distribution Date"]))
    actions, unresolved = [], []
    for event in events:
        if event["symbol"] != "2330":
            continue
        match = rows.get(event["date"])
        if match is None or abs(match[0] - number(event["cash_amount"])) > CASH_TOLERANCE or match[1] < source_date(event["date"]):
            unresolved.append({**event, "reason": "發行人快照缺資料或與交易所事件不一致。"})
            continue
        cash, payment = match
        actions.append({"symbol": "2330", "date": event["date"], "cash_dividend": float(cash),
                        "cash_payment_date": payment.isoformat(), "share_ratio": 1.0,
                        "source": "TWSE_TWT49U+TSMC_official_browser_capture",
                        "official_cash_amount": event["cash_amount"], "payment_date_source": issuer,
                        "capture_digest": digest(capture), "cash_match_tolerance": float(CASH_TOLERANCE)})
    return {"actions": actions, "unresolved": unresolved, "coverage": []}


class IsinTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_isin(html, symbols, observed_on):
    parser = IsinTable()
    parser.feed(html)
    fields, facts, seen = None, [], set()
    for values in parser.rows:
        if {"有價證券代號及名稱", "上市日", "市場別"}.issubset(values):
            fields = values
            continue
        if fields is None or len(values) != len(fields):
            continue
        row = dict(zip(fields, values, strict=True))
        label = row["有價證券代號及名稱"].split()
        if not label or label[0] not in symbols:
            continue
        symbol = label[0]
        if symbol in seen:
            raise ValueError("duplicate ISIN listing fact")
        seen.add(symbol)
        facts.append({"symbol": symbol, "listed_on": source_date(row["上市日"]).isoformat(),
                      "market": row["市場別"], "current_industry": row.get("產業別"),
                      "source": "TWSE_ISIN_current_directory", "observed_on": observed_on})
    if fields is None:
        raise ValueError("ISIN listing schema not recognized")
    return {"listing_facts": facts, "membership": [], "historical_membership_certified": False,
            "missing_symbols": sorted(set(symbols) - seen)}


def collect(output, symbols, start, end, session=None, db=None):
    validate_symbols(symbols)
    start, end = source_date(start), source_date(end)
    if start > end or end.year - start.year >= 20:
        raise ValueError("ordered date range limited to twenty calendar years")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    observed = datetime.now(ZoneInfo("Asia/Taipei")).isoformat()
    save_new(output / "started.json", {"observed_at": observed, "start": start.isoformat(), "end": end.isoformat(), "symbols": symbols})
    session = requests.Session() if session is None else session
    artifacts, events, unresolved = [], [], []

    def fetch(url, params, name):
        reply = session.get(url, params=params, timeout=30, headers={"User-Agent": "tw-stock-analysis/research-source-check"})
        reply.raise_for_status()
        path = raw / name
        with path.open("xb") as stream:
            stream.write(reply.content)
        artifacts.append({"path": str(path.relative_to(output)), "sha256": file_hash(path),
                          "url": url, "params": params, "observed_at": observed})
        return reply.content

    try:
        for year in range(start.year, end.year + 1):
            first, last = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
            params = {"startDate": first.strftime("%Y%m%d"), "endDate": last.strftime("%Y%m%d"), "response": "json"}
            content = fetch(EXRIGHT, params, f"exright_{year}.json")
            parsed = parse_exright(json.loads(content.decode("utf-8-sig")), symbols, first, last)
            events.extend(parsed["events"])
            unresolved.extend(parsed["unresolved"])
        content = fetch(ISIN, {"strMode": "2"}, "isin_twse.html")
        try:
            html = content.decode("cp950")
        except UnicodeDecodeError:
            html = content.decode("utf-8-sig")
        listing = parse_isin(html, symbols, observed)
        if db is None:
            from src.config import get_db

            db = get_db()
        fields = {"_id": 0, "stock_id": 1, "cash_ex_dividend_date": 1, "cash_earnings_distribution": 1,
                  "cash_statutory_surplus": 1, "cash_dividend_payment_date": 1}
        rows = list(db["dividend_detail"].find({"stock_id": {"$in": symbols}}, fields))
        native = raw / "dividend_detail.json"
        save_new(native, json.loads(json.dumps(rows, default=str, allow_nan=False)))
        artifacts.append({"path": str(native.relative_to(output)), "sha256": file_hash(native),
                          "source": "MongoDB.dividend_detail", "observed_at": observed})
        reconciled = reconcile_cash(events, rows)
        unresolved.extend(reconciled["unresolved"])
        evidence = {"actions": reconciled["actions"], "listing_facts": listing["listing_facts"],
                "coverage": [], "membership": [], "tradability": []}
        save_new(output / "evidence.json", evidence)
        save_new(output / "listing_facts.json", listing)
        save_new(output / "unresolved.json", unresolved)
        manifest = {"certified_complete": False, "artifacts": artifacts, "symbols": symbols,
                    "start": start.isoformat(), "end": end.isoformat(), "observed_at": observed,
                    "cash_match_tolerance": str(CASH_TOLERANCE),
                    "limitations": ["官方除權息事件不涵蓋所有股數權利、減資與下市結算。",
                                    "發放日來自既有 FinMind 明細，來源已保留，非交易所直接認證。",
                                    "目前 ISIN 目錄只提供上市事實，不認證歷史股票池或產業。",
                                    "不以空回應證明無公司行動；不自動產生可交易旗標或零值覆蓋。"]}
        save_new(output / "manifest.json", manifest)
        result = {"status": "partial_evidence", "actions": len(evidence["actions"]),
                  "listing_facts": len(listing["listing_facts"]), "unresolved": len(unresolved),
                  "output": str(output), "certified_complete": False}
        save_new(output / "result.json", result)
        return result
    except (requests.RequestException, ValueError, TypeError, OSError, KeyError, UnicodeError) as exc:
        save_new(output / "failure.json", {"error": str(exc), "artifacts": artifacts, "certified_complete": False})
        raise