#!/usr/bin/env python3
"""四維價值畫像 (供 LLM 情境 / 顯示,非量化排序因子——DCF當因子回測無效)。

維1 財務:ROIC(NOPAT/投入資本)、ROE、負債
維2 護城河:營益率 水準/穩定度/趨勢(高且穩=護城河)
維3 治理:連續配息年數(一致性 proxy;insider/大股東資料太稀疏不用)
維4 估值:DCF 合理價/安全邊際(讀 stock_factors,已算)

用法: from src.analysis.value_profile import value_profile, value_profile_text
"""
from statistics import mean, pstdev

from bson.decimal128 import Decimal128


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


def _recent_quarters(db, sym, n=8):
    return list(db.quarterly_earnings.find(
        {"symbol": sym},
        {"_id": 0, "year": 1, "season": 1, "income": 1, "balance": 1}
    ).sort([("year", -1), ("season", -1)]).limit(n))


def _roic(qs):
    """近4季營業利益加總 × (1-0.2) / 投入資本(最新有值季的 總資產-流動負債)。"""
    ops = [_f((q.get("income") or {}).get("operating_income")) for q in qs[:4]]
    ops = [o for o in ops if o is not None]
    if len(ops) < 4:
        return None
    nopat = sum(ops) * 0.8
    for q in qs:
        b = q.get("balance") or {}
        ta, cl = _f(b.get("total_assets")), _f(b.get("current_liabilities"))
        if ta and cl and (ta - cl) > 0:
            return round(nopat / (ta - cl) * 100, 1)
    return None


def _op_margin(qs):
    ms = [_f((q.get("income") or {}).get("operating_margin")) for q in qs]
    ms = [m for m in ms if m is not None]
    if not ms:
        return None
    latest = ms[0]
    avg = round(mean(ms), 1)
    std = round(pstdev(ms), 1) if len(ms) > 1 else 0.0
    # 趨勢：最近2季均值 vs 較早2季均值
    trend = "持平"
    if len(ms) >= 4:
        recent, older = mean(ms[:2]), mean(ms[2:4])
        if recent > older + 1:
            trend = "↗上升"
        elif recent < older - 1:
            trend = "↘下滑"
    return {"latest": latest, "avg": avg, "std": std, "trend": trend}


def _payout_years(db, sym):
    """連續配現金股利年數(治理/一致性 proxy)。"""
    rows = list(db.dividend_detail.find(
        {"stock_id": sym}, {"_id": 0, "date": 1, "cash_earnings_distribution": 1}
    ).sort("date", -1))
    years = {}
    for r in rows:
        y = str(r.get("date"))[:4]
        cash = _f(r.get("cash_earnings_distribution")) or 0
        if cash > 0:
            years[y] = True
    if not years:
        return 0
    ys = sorted(years.keys(), reverse=True)
    cnt = 0
    prev = None
    for y in ys:
        if prev is None or int(prev) - int(y) == 1:
            cnt += 1
            prev = y
        else:
            break
    return cnt


def value_profile(db, sym):
    qs = _recent_quarters(db, sym, 8)
    f = db.stock_factors.find_one({"symbol": sym}, sort=[("date", -1)]) or {}
    om = _op_margin(qs)
    # 循環股偵測 → DCF/合理價在衰退期易高估(價值陷阱)：
    #   (a) 營益率變異係數 >0.4(擺盪大)  或
    #   (b) 從高位明顯下滑(衰退段):趨勢下滑 且 曾高(均≥15) 且 目前 < 均×0.7
    cyclical = False
    if om and om["avg"]:
        cv = om["std"] / abs(om["avg"])
        cyclical = cv > 0.4 or (om["trend"] == "↘下滑" and om["avg"] >= 15 and om["latest"] < om["avg"] * 0.7)
    return {
        "roic": _roic(qs),
        "roe": _f(f.get("roe")),
        "debt_ratio": _f(f.get("debt_ratio")),
        "op_margin": om,
        "cyclical": cyclical,
        "payout_years": _payout_years(db, sym),
        "fair_value": _f(f.get("fair_value")),
        "margin_of_safety": _f(f.get("margin_of_safety")),
    }


def value_profile_text(db, sym):
    p = value_profile(db, sym)
    parts = []
    # 維1 財務
    fin = []
    if p["roic"] is not None:
        fin.append(f"ROIC{p['roic']}%")
    if p["roe"] is not None:
        fin.append(f"ROE{p['roe']:.1f}%")
    if p["debt_ratio"] is not None:
        fin.append(f"負債{p['debt_ratio']:.0f}%")
    if fin:
        parts.append("財務:" + " ".join(fin))
    # 維2 護城河
    om = p["op_margin"]
    if om:
        cv = (om["std"] / om["avg"]) if om["avg"] else 9      # 變異係數(相對穩定度)
        if om["avg"] >= 15 and cv < 0.20:
            moat = "高且穩(護城河強)"
        elif cv < 0.20:
            moat = "穩定"
        else:
            moat = "波動大(無護城河)"
        parts.append(f"護城河:營益率{om['latest']}%(近8季均{om['avg']}±{om['std']} {om['trend']},{moat})")
    # 維3 治理
    if p["payout_years"]:
        parts.append(f"治理:連配{p['payout_years']}年")
    # 維4 估值(循環股警示 DCF 陷阱)
    if p["fair_value"]:
        mos = p["margin_of_safety"]
        est = f"估值:DCF合理價{p['fair_value']}" + (f" 安全邊際{mos:+.0f}%" if mos is not None else "")
        if p.get("cyclical"):
            est += " ⚠️高度循環股,DCF/合理價在景氣衰退期易高估(價值陷阱),安全邊際勿盡信"
        parts.append(est)
    elif p.get("cyclical"):
        parts.append("⚠️高度循環股(營益率波動大),估值需看景氣位置而非DCF")
    return " | ".join(parts) if parts else "四維價值資料不足"
