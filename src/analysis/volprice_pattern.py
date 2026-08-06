"""量價型態自動標籤(七句量價口訣,加位置過濾)。多時框:週/月/季/半年/年。

依「量增/量縮/量平 × 價漲/跌/平 × 位置(低/中/高位)」→ 七句口訣標籤。
位置維度補口訣的盲點(原口訣只看單根量價,不帶相對高低)。純計算,dashboard 與 MoE 技術委員可共用。

七句口訣:
 1 低位無量·等待 / 高位無量·拿好(防背離)
 2 低位放量·跟上 / 高位放量·跑路
 3 量增價升·果斷買入   4 量縮價升·安心持有   5 量增價跌·及時減倉
 6 量平價跌·堅決出局   7 量平價升·擇機加倉
"""

# 時框 → (期間交易日, 價漲跌門檻%, 量增縮門檻%);時框越長門檻越大(大波動才算漲跌)
TIMEFRAMES = {
    "週":   (5,   3.0,  20.0),
    "月":   (20,  6.0,  15.0),
    "季":   (60,  12.0, 15.0),
    "半年": (120, 20.0, 15.0),
    "年":   (240, 30.0, 15.0),
}


def classify(closes, vols, period, price_th, vol_th, pos_lo=0.33, pos_hi=0.67):
    """closes/vols=日序列(建議還原價)。比較最近 period vs 前一個 period,加位置。回 dict 或 None。"""
    n = len(closes)
    if n < period * 2 or n < 10:
        return None
    cur = closes[-1]
    base = closes[-period - 1] if n > period else closes[0]
    ret = (cur / base - 1) * 100 if base else 0.0
    v_now = sum(vols[-period:]) / period
    prev = vols[-2 * period:-period]
    v_prev = (sum(prev) / len(prev)) if prev else v_now
    vchg = (v_now / v_prev - 1) * 100 if v_prev else 0.0

    volst = "增" if vchg >= vol_th else ("縮" if vchg <= -vol_th else "平")
    prst = "漲" if ret >= price_th else ("跌" if ret <= -price_th else "平")
    win = closes[-min(n, period * 3):]
    lo, hi = min(win), max(win)
    pos_pct = (cur - lo) / (hi - lo) if hi > lo else 0.5
    posst = "低" if pos_pct <= pos_lo else ("高" if pos_pct >= pos_hi else "中")

    fang = volst == "增"     # 放量
    wu = volst in ("縮", "平")  # 無量(縮或平)
    # 位置極端優先(口訣 1、2),再看量價方向(口訣 3–7)
    if posst == "高" and fang:
        lab, emo, tone = "高位放量·跑路", "🔴", "bear"
    elif posst == "低" and fang:
        lab, emo, tone = "低位放量·跟上", "🟢", "bull"
    elif posst == "高" and wu and prst != "跌":
        lab, emo, tone = "高位無量·拿好(防背離)", "🟠", "warn"
    elif posst == "低" and wu and prst != "漲":
        lab, emo, tone = "低位無量·等待", "⚪", ""
    elif volst == "增" and prst == "漲":
        lab, emo, tone = "量增價升·果斷買入", "🟢", "bull"
    elif volst == "縮" and prst == "漲":
        lab, emo, tone = "量縮價升·安心持有", "🔵", "bull"
    elif volst == "增" and prst == "跌":
        lab, emo, tone = "量增價跌·及時減倉", "🟠", "warn"
    elif volst == "平" and prst == "跌":
        lab, emo, tone = "量平價跌·堅決出局", "🔴", "bear"
    elif volst == "平" and prst == "漲":
        lab, emo, tone = "量平價升·擇機加倉", "🟢", "bull"
    else:
        lab, emo, tone = "量價中性·觀望", "⚪", ""
    return {"label": lab, "emoji": emo, "tone": tone,
            "位置": posst, "量": volst, "價": prst,
            "報酬%": round(ret, 1), "量變%": round(vchg, 1), "位階%": round(pos_pct * 100)}


def classify_tf(closes, vols, tf):
    p, pth, vth = TIMEFRAMES[tf]
    return classify(closes, vols, p, pth, vth)
