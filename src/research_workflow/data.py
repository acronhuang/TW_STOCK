import re
from datetime import datetime

import pandas as pd

from .engine import CONSTRAINTS, PRICES, prepare


def validate_symbols(symbols):
    if not symbols or any(re.fullmatch(r"[0-9]{4,6}[A-Z]?", symbol) is None for symbol in symbols):
        raise ValueError("explicit Taiwan stock or ETF symbols required")


def mongo_prices(symbols, start, end, db=None):
    validate_symbols(symbols)
    if db is None:
        from src.config import get_db

        db = get_db()
    fields = ("date", "symbol", *PRICES, *CONSTRAINTS, "cash_payment_date", "industry", "industry_available_at")
    query = {"symbol": {"$in": symbols}, "date": {"$gte": datetime.fromisoformat(start),
                                                  "$lte": datetime.fromisoformat(end)}}
    rows = list(db["stock_price"].find(query, {"_id": 0, **{name: 1 for name in fields}}))
    for row in rows:
        for name in (*PRICES, "cash_dividend", "share_ratio"):
            value = row.get(name)
            if value is not None:
                row[name] = float(value.to_decimal()) if hasattr(value, "to_decimal") else float(value)
    return pd.DataFrame(rows)


def audit(frame):
    required = {"date", "symbol", *PRICES, *CONSTRAINTS}
    missing = sorted(required.difference(frame.columns))
    result = {"status": "blocked", "rows": len(frame), "missing_fields": missing,
              "scope": "input_schema_only_not_historical_universe_certification",
              "limitations": ["欄位存在不代表來源已驗證；另需歷史股票池、下市結算與公司行動來源核對。"]}
    result["missing_values"] = {name: int(frame[name].isna().sum()) for name in required.intersection(frame.columns) if frame[name].isna().any()}
    if "evidence_hash" in frame:
        hashes = frame["evidence_hash"].dropna().unique()
        result["evidence_hash"] = hashes[0] if len(hashes) == 1 else None
    if frame.empty:
        result["error"] = "無資料"
        return result
    if "date" in frame:
        dates = pd.to_datetime(frame["date"])
        result.update(start=str(dates.min().date()), end=str(dates.max().date()))
    if "symbol" in frame:
        result["symbols"] = int(frame["symbol"].nunique())
    if not missing:
        try:
            prepare(frame, strict=True)
            result["status"] = "ready_for_input_validation"
        except (ValueError, TypeError) as exc:
            result["error"] = str(exc)
    return result


def source_inventory(symbols, start, end, db=None):
    validate_symbols(symbols)
    if db is None:
        from src.config import get_db

        db = get_db()
    query = {"symbol": {"$in": symbols}, "date": {"$gte": datetime.fromisoformat(start),
                                                  "$lte": datetime.fromisoformat(end)}}
    count = db["stock_price"].count_documents(query)
    coverage = {name: db["stock_price"].count_documents({**query, name: {"$exists": True, "$ne": None}})
                for name in CONSTRAINTS}
    sources = {}
    for name, key in (("corporate_actions", "symbol"), ("dividend_detail", "stock_id"),
                      ("dividend_results", "stock_id"), ("taiwan_stock_info", "stock_id"), ("delisting", "stock_id")):
        sources[name] = {"records_for_symbols_all_dates": db[name].count_documents({key: {"$in": symbols}}),
                         "certified_complete": False}
    return {"status": "requires_source_attestation" if count else "no_data", "certified_complete": False,
            "symbols": symbols, "start": start, "end": end, "price_records": count,
            "price_evidence_field_counts": coverage, "available_sources": sources,
            "corporate_actions_semantics": "price_adjustment_ratio_not_share_entitlement",
            "requirements": ["歷史交易限制需開盤時已知證據，不以有成交量推定。",
                             "歷史股票池、上市日及產業需有效區間與當時可知時間，不使用最新快照回填。",
                             "公司行動需股數權利、現金與實際發放日，無事件缺省值需完整期間覆蓋證明。",
                             "下市後持倉須有結算或估值證據；存在下市名單不等於已有結算價。"]}