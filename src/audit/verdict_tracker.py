"""AI verdict 品質回饋迴路 —— 事後歸因（命中率 / 校準）。

背景：系統做了大量分析，但缺「分析到底準不準」的回饋。引用正確性只是最低門檻；
真正的品質要看 verdict → N 天後的實際超額報酬。本模組把 verdict 快照與後續價格
比對，算出命中率與分票別校準，供持續優化（換模型/節點/prompt 的 A/B 才有依據）。

設計：純函式核心（可測），DB 存取為薄殼。verdict 統一為 買進/賣出/持有。
"""
from __future__ import annotations

# 持有判定的「無大波動」帶寬：|報酬| ≤ FLAT_BAND 視為持有正確。
FLAT_BAND = 0.03

# final_verdict 可能為 強力買進/買進/觀望/減碼/賣出 等 → 歸一為 買進/賣出/持有。
_VERDICT_MAP = {
    "強力買進": "買進", "買進": "買進", "加碼": "買進", "進場": "買進",
    "賣出": "賣出", "減碼": "賣出", "出場": "賣出",
    "持有": "持有", "觀望": "持有", "中立": "持有",
}


def normalize_verdict(verdict: str) -> str:
    """將多元 verdict 歸一為 買進/賣出/持有（未知→持有）。"""
    return _VERDICT_MAP.get((verdict or "").strip(), "持有")


def forward_return(entry_price: float, later_price: float) -> float | None:
    """(later - entry) / entry。進場價無效（None/<=0）回 None。"""
    if not entry_price or entry_price <= 0 or later_price is None:
        return None
    return (later_price - entry_price) / entry_price


def excess_return(stock_ret: float, market_ret: float) -> float | None:
    """超額報酬 = 個股報酬 - 大盤/母體報酬。任一為 None 回 None。

    市場相對命中 = is_hit(verdict, excess_return(...))，比絕對 +3% 公平（排除大盤題材）。
    """
    if stock_ret is None or market_ret is None:
        return None
    return stock_ret - market_ret


def is_hit(verdict: str, ret: float, flat_band: float = FLAT_BAND) -> bool:
    """依票別判定 verdict 是否命中。

    買進：報酬 > band → 命中；賣出：報酬 < -band → 命中；
    持有：|報酬| ≤ band（沒大波動）→ 命中。
    """
    if ret is None:
        return False
    if verdict == "買進":
        return ret > flat_band
    if verdict == "賣出":
        return ret < -flat_band
    if verdict == "持有":
        return abs(ret) <= flat_band
    return False


def evaluate_verdict(record: dict, later_price: float) -> dict | None:
    """比對單筆 verdict 與後續價格。進場價無效回 None。

    record: {symbol, verdict|final_verdict, entry_price|price_at_analysis, ...}
    回傳 {symbol, verdict, entry_price, later_price, ret, hit}
    """
    entry = record.get("entry_price", record.get("price_at_analysis"))
    ret = forward_return(entry, later_price)
    if ret is None:
        return None
    verdict = normalize_verdict(record.get("verdict", record.get("final_verdict", "持有")))
    return {
        "symbol": record.get("symbol"),
        "verdict": verdict,
        "entry_price": entry,
        "later_price": later_price,
        "ret": ret,
        "hit": is_hit(verdict, ret),
    }


def compute_metrics(evaluated: list[dict]) -> dict:
    """彙總命中率（整體 + 分票別）。

    回傳 {n, hits, hit_rate, avg_return, by_verdict: {票別: {n, hits, hit_rate}}}
    """
    n = len(evaluated)
    if n == 0:
        return {"n": 0, "hits": 0, "hit_rate": None, "avg_return": None, "by_verdict": {}}

    hits = sum(1 for e in evaluated if e.get("hit"))
    rets = [e["ret"] for e in evaluated if e.get("ret") is not None]
    by = {}
    for e in evaluated:
        v = e.get("verdict", "持有")
        b = by.setdefault(v, {"n": 0, "hits": 0})
        b["n"] += 1
        b["hits"] += 1 if e.get("hit") else 0
    for v, b in by.items():
        b["hit_rate"] = b["hits"] / b["n"] if b["n"] else None

    return {
        "n": n,
        "hits": hits,
        "hit_rate": hits / n,
        "avg_return": (sum(rets) / len(rets)) if rets else None,
        "by_verdict": by,
    }


def count_trailing_drops(values) -> int:
    """尾端連續嚴格下滑的步數（純函式，可測）。

    values 依時間遞增排列。持平（相等）視為中斷，不計入。
    例：[0.5, 0.6, 0.55, 0.5] → 2。
    """
    if not values:
        return 0
    drops = 0
    for i in range(len(values) - 1, 0, -1):
        if values[i] < values[i - 1]:
            drops += 1
        else:
            break
    return drops


def build_hitrate_alert(series, max_consecutive_drops: int = 3, floor=None):
    """命中率趨勢告警判定（純函式，可測）。

    series: [(ts, value)] 依時間遞增。觸發條件（任一）→ 回警報 dict，否則 None：
      ① 尾端連續下滑 >= max_consecutive_drops 期
      ② 最新值 < floor（若有設 floor）
    """
    values = [v for _, v in (series or [])]
    if not values:
        return None
    drops = count_trailing_drops(values)
    latest = values[-1]
    reasons = []
    if max_consecutive_drops and drops >= max_consecutive_drops:
        reasons.append(f"連 {drops} 期下滑")
    if floor is not None and latest < floor:
        reasons.append(f"最新 {latest:.1%} 跌破地板 {floor:.0%}")
    if not reasons:
        return None
    return {
        "level": "warning",
        "message": ("AI 命中率警示：" + "、".join(reasons)
                    + f"（最新 {latest:.1%}），建議檢視模型/prompt/資料品質。"),
        "detail": {"latest": latest, "consecutive_drops": drops,
                   "floor": floor, "n_points": len(values)},
    }
