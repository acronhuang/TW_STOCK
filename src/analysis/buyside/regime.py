"""大盤市況(regime)分類 — 依 TAIEX 近 N 日趨勢分 多頭/盤整/空頭。

v4 regime-aware 用:多區間驗證顯示買進追高反轉集中在趨勢市,盤整市買進反而達標;
故品質 tilt 只該套在趨勢市。
"""
from __future__ import annotations

from datetime import datetime

from bson.decimal128 import Decimal128


def _to_f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify_regime(db, date, lookback: int = 20, thr: float = 3.0,
                    market: str = "TAIEX") -> str | None:
    """回 '多頭'/'盤整'/'空頭'/None。以 market 近 lookback 交易日 % 變動 vs ±thr% 判定。"""
    d = date if isinstance(date, datetime) else datetime.fromisoformat(str(date)[:10])
    ps = list(db["stock_price"].find(
        {"symbol": market, "date": {"$lte": d}}, {"close": 1}
    ).sort("date", -1).limit(lookback + 1))
    if len(ps) < lookback + 1:
        return None
    now = _to_f(ps[0]["close"])
    ago = _to_f(ps[-1]["close"])
    if not ago:
        return None
    chg = (now - ago) / ago * 100
    return "多頭" if chg > thr else ("空頭" if chg < -thr else "盤整")
