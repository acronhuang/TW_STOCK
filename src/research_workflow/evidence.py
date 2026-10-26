import numpy as np
import pandas as pd

from .registry import digest


def enrich(prices, evidence):
    result = prices.copy()
    result["symbol"] = result["symbol"].astype(str)
    stamps = pd.to_datetime(result["date"])
    native = result.copy()
    for name in ("eligible", "listed_on", "can_buy", "can_sell", "cash_dividend", "share_ratio"):
        if name not in result:
            result[name] = pd.Series(np.nan, index=result.index, dtype=object)

    def assign(mask, name, value):
        if name in native:
            known = native.loc[mask, name].dropna()
            if len(known) and not known.eq(value).all():
                raise ValueError(f"conflicting evidence for {name}")
        if name not in result:
            result[name] = pd.Series(np.nan, index=result.index, dtype=object)
        result.loc[mask, name] = value

    def interval(row):
        if not isinstance(row.get("source"), str) or not row["source"].strip():
            raise ValueError("evidence source required")
        start, end = pd.Timestamp(row["start"]), pd.Timestamp(row["end"])
        if start > end:
            raise ValueError("invalid evidence coverage interval")
        return result["symbol"].eq(str(row["symbol"])) & stamps.between(start, end)

    for row in evidence.get("coverage", []):
        mask = interval(row)
        if row.get("kind") != "corporate_actions" or row.get("complete") is not True:
            raise ValueError("explicit complete corporate_actions coverage required")
        for name, value in (("cash_dividend", 0.0), ("share_ratio", 1.0)):
            result.loc[mask & result[name].isna(), name] = value
    seen = set()
    for row in evidence.get("actions", []):
        if "share_ratio" not in row or "cash_dividend" not in row:
            raise ValueError("explicit cash_dividend and share_ratio required; price ratio is not shares")
        key = (str(row["symbol"]), str(row["date"]))
        if key in seen:
            raise ValueError("duplicate corporate action; aggregate entitlements explicitly")
        seen.add(key)
        mask = interval({**row, "start": row["date"], "end": row["date"]})
        if not np.isfinite(row["share_ratio"]) or row["share_ratio"] <= 0 or not np.isfinite(row["cash_dividend"]) or row["cash_dividend"] < 0:
            raise ValueError("invalid corporate action entitlement")
        assign(mask, "cash_dividend", float(row["cash_dividend"]))
        assign(mask, "share_ratio", float(row["share_ratio"]))
        if row["cash_dividend"] > 0:
            if not row.get("cash_payment_date"):
                raise ValueError("cash dividend requires actual payment date")
            assign(mask, "cash_payment_date", row["cash_payment_date"])
    for row in evidence.get("listing_facts", []):
        if not row.get("source") or not row.get("observed_on"):
            raise ValueError("listing fact source and observation time required")
        listed = pd.Timestamp(row["listed_on"])
        observed = pd.Timestamp(row["observed_on"])
        if pd.isna(listed) or pd.isna(observed) or listed.date() > observed.date():
            raise ValueError("invalid observed listing fact")
        mask = result["symbol"].eq(str(row["symbol"]))
        assign(mask, "listed_on", listed.date().isoformat())
    for row in evidence.get("membership", []):
        mask = interval(row)
        available = pd.Timestamp(row["available_at"])
        mask &= stamps.map(lambda stamp, known_at=available: known_at.to_pydatetime() <= stamp.to_pydatetime().replace(hour=13, minute=30))
        if not isinstance(row.get("eligible"), bool):
            raise TypeError("explicit membership eligibility required")
        assign(mask, "eligible", row["eligible"])
        assign(mask, "listed_on", row["listed_on"])
        if row.get("industry"):
            assign(mask, "industry", row["industry"])
            assign(mask, "industry_available_at", row["available_at"])
    for row in evidence.get("tradability", []):
        mask = interval({**row, "start": row["date"], "end": row["date"]})
        if pd.Timestamp(row["available_at"]) > pd.Timestamp(row["date"]) + pd.Timedelta(hours=9):
            raise ValueError("tradability evidence was unavailable at execution open")
        for name in ("can_buy", "can_sell"):
            if not isinstance(row.get(name), bool):
                raise TypeError("explicit tradability flags required")
            assign(mask, name, row[name])
    for name in ("cash_dividend", "share_ratio"):
        result[name] = pd.to_numeric(result[name], errors="raise")
    result["evidence_hash"] = digest(evidence)
    return result