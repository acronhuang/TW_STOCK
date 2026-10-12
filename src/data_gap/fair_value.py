"""停機日補算的合理價欄位。

evening_pipeline 的 backfill_valuation_factors 只算「最新因子日」。停機漏掉的日子用同一套 DCF+DDM+PE Band 綜合價
（ValuationAnalyzer.analyze），僅把股價換成該日收盤，並以 fair_value_source 標明來源。
最初曾只用 DCF+DDM 補算，與前後日的綜合價差一截（2330：625 對 1085），已改正；舊標記保留在 REPLACEABLE 以便重算覆蓋。
"""
from __future__ import annotations

SOURCE = "composite_asof_price"
REPLACEABLE = ("pit_dcf_ddm", SOURCE)


def fields(fair_value: float | None, price: float | None) -> dict | None:
    if not fair_value or fair_value <= 0:
        return None
    out = {"fair_value": round(float(fair_value), 2)}
    if price and price > 0:
        out["margin_of_safety"] = round((fair_value - price) / price * 100, 2)
    out["fair_value_source"] = SOURCE
    return out
