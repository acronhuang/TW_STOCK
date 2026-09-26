"""M1 買方特徵萃取器（純函式,免 DB)。

把「動能 + 價值(PE/PB 百分位) + 品質(ROE)」整理成再評分器要的特徵;
缺 PE/ROE 時標記 coverage_ok=False(→ 再評分器維持原判,不亂動)。
"""
from __future__ import annotations

from bisect import bisect_left


def pctile_rank(value, universe) -> float | None:
    """value 在 universe 的百分位（0–100)。universe 空 → None。

    採 searchsorted(left)/len*100,與專案既有 PE Band / verdict 百分位口徑一致。
    """
    if value is None or not universe:
        return None
    arr = sorted(u for u in universe if u is not None)
    if not arr:
        return None
    return bisect_left(arr, value) / len(arr) * 100.0


def extract_buy_features(rec: dict, universe: dict) -> dict:
    """rec: {prior_20d, pe, pb, roe};universe: {pe:[...], pb:[...]}。

    回 {prior_20d, pe_pctile, pb_pctile, roe, coverage_ok}。
    coverage_ok:PE 與 ROE 皆有值(再評分所需的最小特徵集)。
    """
    pe = rec.get("pe")
    pb = rec.get("pb")
    roe = rec.get("roe")
    pe_pctile = pctile_rank(pe, universe.get("pe", [])) if pe is not None else None
    pb_pctile = pctile_rank(pb, universe.get("pb", [])) if pb is not None else None
    roe_pctile = pctile_rank(roe, universe.get("roe", [])) if roe is not None else None
    coverage_ok = pe is not None and roe is not None and pe_pctile is not None
    return {
        "prior_20d": rec.get("prior_20d"),
        "pe_pctile": pe_pctile,
        "pb_pctile": pb_pctile,
        "roe": roe,
        "roe_pctile": roe_pctile,
        "coverage_ok": coverage_ok,
    }
