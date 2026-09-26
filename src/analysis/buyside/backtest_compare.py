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


def compare(db, window: int = 20) -> dict:
    """回 {v1, v2, downgraded}。v2 = buy_v2 仍為『買進』的子集。"""
    rows = list(db["verdict_detail"].find({"window": window, "verdict": "買進"}))
    v2_rows = [r for r in rows if r.get("buy_v2", "買進") == "買進"]
    v1, v2 = _stats(rows), _stats(v2_rows)
    delta_hit = (v2["hit_rate"] - v1["hit_rate"]) if (v1["hit_rate"] is not None and v2["hit_rate"] is not None) else None
    delta_ex = (v2["mean_excess"] - v1["mean_excess"]) if (v1["mean_excess"] is not None and v2["mean_excess"] is not None) else None
    return {"v1": v1, "v2": v2, "downgraded": len(rows) - len(v2_rows),
            "delta_hit": delta_hit, "delta_excess": delta_ex}
