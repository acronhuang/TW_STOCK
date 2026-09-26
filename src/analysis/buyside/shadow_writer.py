"""M3 影子寫入器 — 對 verdict_detail 的買進列算 buy_v2,只寫 shadow 欄。

嚴格影子:絕不改 verdict / final_verdict;可 --dry-run。
特徵取自 stock_factors(PE/PB/ROE),百分位以全市場 universe 計。
"""
from __future__ import annotations

from bson.decimal128 import Decimal128

from src.analysis.buyside.features import extract_buy_features
from src.analysis.buyside.buy_rescore import rescore


def _to_f(v):
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_universe(db) -> dict:
    """最新一日横切面因子的 PE/PB 清單(百分位母體)。取最新 date 而非全歷史,
    避免真實庫掃百萬筆;亦更符合「當前横切面」的百分位語意。"""
    latest = db["stock_factors"].find_one({}, {"date": 1}, sort=[("date", -1)])
    q = {"date": latest["date"]} if latest else {}
    pe, pb, roe = [], [], []
    for f in db["stock_factors"].find(q, {"pe_ratio": 1, "pb_ratio": 1, "roe": 1}):
        p = _to_f(f.get("pe_ratio"))
        b = _to_f(f.get("pb_ratio"))
        rv = _to_f(f.get("roe"))
        if p is not None:
            pe.append(p)
        if b is not None:
            pb.append(b)
        if rv is not None:
            roe.append(rv)
    return {"pe": pe, "pb": pb, "roe": roe}


def run_shadow(db, window: int = 20, dry_run: bool = False,
               scorer=rescore, field: str = "buy_v2") -> int:
    """對指定 window 的所有『買進』列寫 buy_v2 shadow。回處理筆數。"""
    uni = build_universe(db)
    n = 0
    for r in db["verdict_detail"].find({"window": window, "verdict": "買進"}):
        fac = db["stock_factors"].find_one({"symbol": r.get("symbol")}, sort=[("date", -1)])
        rec = {
            "prior_20d": r.get("prior_20d"),
            "pe": _to_f(fac.get("pe_ratio")) if fac else None,
            "pb": _to_f(fac.get("pb_ratio")) if fac else None,
            "roe": _to_f(fac.get("roe")) if fac else None,
        }
        res = scorer(extract_buy_features(rec, uni))
        if not dry_run:
            db["verdict_detail"].update_one(
                {"_id": r["_id"]},
                {"$set": {field: res["v2"], f"{field}_reason": res["reason"],
                          f"{field}_score": res["score"]}})
        n += 1
    return n


def run_shadow_cohort_quality(db, window: int = 20, field: str = "buy_v3c",
                              pctile_lo: float = 25.0, dry_run: bool = False) -> dict:
    """v3.1 群體相對純品質:買進『群體內』ROE 底 pctile_lo → 降級持有。

    兩趟:先收集買進群 ROE 定 cutoff(修正 v3 用全市場母體→買進偏高品質幾乎不觸發)。
    回 {n, cut, downgraded}。
    """
    import numpy as np
    buys = list(db["verdict_detail"].find({"window": window, "verdict": "買進"}))
    roes = {}
    for r in buys:
        fac = db["stock_factors"].find_one({"symbol": r.get("symbol")}, sort=[("date", -1)])
        roes[r["_id"]] = _to_f(fac.get("roe")) if fac else None
    have = [v for v in roes.values() if v is not None]
    cut = float(np.quantile(have, pctile_lo / 100.0)) if have else None
    n = dg = 0
    for r in buys:
        rv = roes[r["_id"]]
        low = cut is not None and rv is not None and rv <= cut
        v2 = "降級持有" if low else "買進"
        if low:
            dg += 1
        if not dry_run:
            db["verdict_detail"].update_one({"_id": r["_id"]}, {"$set": {field: v2}})
        n += 1
    return {"n": n, "cut": cut, "downgraded": dg}
