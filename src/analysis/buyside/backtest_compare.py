"""M4 回測比較器 — 同一 verdict_detail 集,買方 v1(全買進)vs v2(未被降級者)對照。

v2 買進集 = buy_v2 仍為『買進』者(降級持有者移出)。比較命中率與均超額,
量化「影子改良」是否真的提升買方 alpha。純讀取,不寫入。
"""
from __future__ import annotations

from statistics import mean


def _stats(subset: list[dict]) -> dict:
    hv = [r for r in subset if r.get("hit") is not None]
    hits = [r for r in hv if r["hit"] is True]
    ex = [r["excess"] for r in subset if r.get("excess") is not None]
    return {
        "n": len(subset),
        "hit_rate": (len(hits) / len(hv)) if hv else None,
        "mean_excess": mean(ex) if ex else None,
    }


def compare(db, window: int = 20, field: str = "buy_v2") -> dict:
    """回 {v1, v2, downgraded}。v2 = {field} 仍為『買進』的子集(預設 buy_v2;可傳 buy_v3)。"""
    rows = list(db["verdict_detail"].find({"window": window, "verdict": "買進"}))
    v2_rows = [r for r in rows if r.get(field, "買進") == "買進"]
    v1, v2 = _stats(rows), _stats(v2_rows)
    delta_hit = (v2["hit_rate"] - v1["hit_rate"]) if (v1["hit_rate"] is not None and v2["hit_rate"] is not None) else None
    delta_ex = (v2["mean_excess"] - v1["mean_excess"]) if (v1["mean_excess"] is not None and v2["mean_excess"] is not None) else None
    return {"v1": v1, "v2": v2, "downgraded": len(rows) - len(v2_rows),
            "delta_hit": delta_hit, "delta_excess": delta_ex}


def eval_v5_shadow(db, window: int = 20, date_lo: str = None, date_hi: str = None) -> dict:
    """把 team_analysis.advisor_v5_rating(影子)接回 verdict_detail 的前瞻超額,
    比較『live-買進』全集 vs 『v5-買進(未被 v5 降級)』子集 —— 分整體/趨勢/盤整。

    date_lo/date_hi:限定 verdict date 區間(供時間切段 out-of-sample)。回 dict。
    """
    # (symbol,date) -> advisor_v5_rating / regime
    shadow = {}
    for a in db["team_analysis"].find(
            {"advisor_v5_rating": {"$exists": True}},
            {"symbol": 1, "date": 1, "advisor_v5_rating": 1, "advisor_v5_regime": 1}):
        shadow[(a["symbol"], str(a.get("date"))[:10])] = (
            a.get("advisor_v5_rating"), a.get("advisor_v5_regime"))

    rows = []
    for d in db["verdict_detail"].find({"window": window, "verdict": "買進"},
                                       {"symbol": 1, "date": 1, "excess": 1, "hit": 1}):
        ds = str(d.get("date"))[:10]
        if date_lo and ds < date_lo:
            continue
        if date_hi and ds >= date_hi:
            continue
        rat, reg = shadow.get((d["symbol"], ds), (None, None))
        if rat is None:
            continue                      # 尚無影子評級 → 不計
        rows.append({"excess": d.get("excess"), "hit": d.get("hit"),
                     "reg": reg, "v5_buy": rat in ("買進", "強力買進")})

    def block(g):
        live = g
        v5 = [x for x in g if x["v5_buy"]]
        return {"live": _stats(live), "v5": _stats(v5), "downgraded": len(live) - len(v5)}

    out = {"overall": block(rows)}
    for reg in ("多頭", "盤整", "空頭"):
        g = [x for x in rows if x["reg"] == reg]
        if g:
            out[reg] = block(g)
    return out
