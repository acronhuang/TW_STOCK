"""套牢部位:滾動解套 vs 停損 判斷(規則式)。

哲學(拒絕死扛與盲目補倉,籌碼滾動解套):套牢不是「抱 or 砍」二元——
- 結構性轉壞(空頭崩壞 / 大戶倒貨 / 跌破所有支撐)→ 建議停損
- 箱型 / 跌深有撐 + 籌碼穩 → 可滾動解套(高拋低吸降成本),給參考價位

用價=原始價(對齊持倉成本 avg_cost)。三訊號:量價型態(月/季)+支撐壓力+大戶集保。純計算。
"""
from datetime import timedelta

import pandas as pd

from src.analysis.tech_lines import sr_levels
from src.analysis.volprice_pattern import classify_tf


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def _load(db, symbol, days=420):
    lat = db.stock_price.find_one({"stock_id": symbol, "date": {"$type": "date"}}, sort=[("date", -1)])
    if not lat:
        return None
    rows = []
    for r in db.stock_price.find(
            {"stock_id": symbol, "date": {"$gte": lat["date"] - timedelta(days=days), "$type": "date"}},
            {"date": 1, "high": 1, "low": 1, "close": 1, "volume": 1}).sort("date", 1):
        c = _g(r.get("close"))
        if c:
            rows.append({"high": _g(r.get("high")) or c, "low": _g(r.get("low")) or c,
                         "close": c, "volume": _g(r.get("volume")) or 0})
    return pd.DataFrame(rows) if rows else None


def _big400_change(db, symbol):
    """集保大戶(>400張)最新 vs 約1個月前的百分點變化。"""
    rows = list(db.shareholding.find({"stock_id": symbol}, {"big400_pct": 1}).sort("date", -1).limit(6))
    if len(rows) < 2:
        return None, None
    now = rows[0].get("big400_pct")
    old = rows[min(4, len(rows) - 1)].get("big400_pct")
    chg = (now - old) if (now is not None and old is not None) else None
    return now, chg


def assess(db, symbol, cost, px=None, trap_th=-3.0):
    """回 dict:trapped/verdict(可滾動解套/建議停損/觀察/未套牢)/roll_buy/roll_sell/reasons。"""
    df = _load(db, symbol)
    if df is None or len(df) < 60 or not cost:
        return None
    cur = px or float(df["close"].iloc[-1])
    pnl = (cur / cost - 1) * 100
    trapped = pnl <= trap_th

    closes, vols = df["close"].tolist(), df["volume"].tolist()
    vp_m = classify_tf(closes, vols, "月")
    vp_q = classify_tf(closes, vols, "季")
    sr = sr_levels(df)
    sup = [s for s in sr.get("support", []) if s["price"] < cur]
    res = [r for r in sr.get("resistance", []) if r["price"] > cur]
    near_sup = max(sup, key=lambda s: s["price"]) if sup else None
    near_res = min(res, key=lambda r: r["price"]) if res else None
    _big, big_chg = _big400_change(db, symbol)

    score, reasons = 0.0, []
    for vp, w in ((vp_m, 1.0), (vp_q, 0.5)):
        if not vp:
            continue
        lab = vp["label"]
        if any(b in lab for b in ("量增價跌", "量平價跌", "跑路")):
            score -= 2 * w
            if w == 1.0:
                reasons.append(f"月線{lab}(空頭)")
        elif any(h in lab for h in ("低位無量", "低位放量", "中性", "量縮價跌")):
            score += 1 * w
    if near_sup and (cur / near_sup["price"] - 1) <= 0.10:
        score += 2
        reasons.append(f"跌深有撐{near_sup['price']:.1f}")
    elif not sup:
        score -= 2
        reasons.append("下方無支撐(破線)")
    if big_chg is not None:
        if big_chg <= -1.5:
            score -= 2
            reasons.append(f"大戶減碼{big_chg:+.1f}pt")
        elif big_chg >= 0:
            score += 1
            reasons.append("大戶未減")

    if not trapped:
        verdict = "未套牢"
    elif score >= 1:
        verdict = "可滾動解套"
    elif score <= -2:
        verdict = "建議停損"
    else:
        verdict = "觀察(結構未明)"
    return {"trapped": trapped, "pnl": round(pnl, 1), "verdict": verdict, "score": round(score, 1),
            "reasons": reasons, "roll_buy": near_sup["price"] if near_sup else None,
            "roll_sell": near_res["price"] if near_res else None,
            "vp_month": vp_m["label"] if vp_m else None, "big_chg": big_chg}


def context_line(db, symbol, cost, px=None):
    """給持倉風控委員 context 的一行(僅套牢時輸出)。"""
    a = assess(db, symbol, cost, px)
    if not a or not a["trapped"]:
        return ""
    if a["verdict"] == "可滾動解套":
        rb = f"低吸{a['roll_buy']:.1f}" if a["roll_buy"] else "低吸=貼近支撐分批"
        rs = f"高拋{a['roll_sell']:.1f}" if a["roll_sell"] else "高拋=前高/壓力"
        tip = f"(建議高拋低吸降成本:{rs}/{rb})"
    elif a["verdict"] == "建議停損":
        tip = "(結構轉壞,勿死扛勿盲補)"
    else:
        tip = ""
    why = ";".join(a["reasons"][:3])
    return f"套牢評估({a['pnl']:+.1f}%): {a['verdict']}{tip} —— {why}"
