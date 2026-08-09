"""技術線共用模組:費波納契反彈 + 支撐壓力線(原始價)。

dashboard 與 MoE 技術委員共用同一真相源。純計算,無 LLM 依賴。
"""
import csv
import glob
import os
from datetime import timedelta

import pandas as pd

_SCAN_DIR = "/home/mdsadmin/Stock/tw-stock-analysis/results"


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def price_series(db, symbol, lookback_days=180):
    """回傳原始價 DataFrame(date/open/high/low/close/volume),近 lookback_days 天。"""
    lat = db.stock_price.find_one({"stock_id": symbol, "date": {"$type": "date"}}, sort=[("date", -1)])
    if not lat:
        return pd.DataFrame()
    end = lat["date"]; start = end - timedelta(days=lookback_days)
    rows = []
    for r in db.stock_price.find({"stock_id": symbol, "date": {"$gte": start, "$lte": end, "$type": "date"}},
                                 {"date": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}).sort("date", 1):
        c = _g(r.get("close"))
        if c:
            rows.append({"date": r["date"], "open": _g(r.get("open")) or c,
                         "high": _g(r.get("high")) or c, "low": _g(r.get("low")) or c, "close": c,
                         "volume": _g(r.get("volume")) or 0})
    return pd.DataFrame(rows)


def fib_rebound(df):
    """費波納契反彈:swing=最高→之後最低,三檔目標+現況。回 dict(含 high/low/current/targets/zone)。"""
    if df is None or len(df) < 20:
        return None
    hi = float(df["high"].max())
    hi_i = int(df.index[df["high"] == hi][-1])
    lo = float(df["low"].iloc[hi_i:].min())
    cur = float(df["close"].iloc[-1])
    drop = hi - lo
    if drop <= 0:
        return None
    t = {k: round(lo + drop * v, 1) for k, v in {"weak": 0.382, "mid": 0.5, "strong": 0.618}.items()}
    if cur <= lo * 1.005:
        zone = "仍在低點/反彈未發動"
    elif cur < t["weak"]:
        zone = "反彈初起(未達弱勢)"
    elif cur < t["mid"]:
        zone = "弱勢反彈區(0.382~0.5)"
    elif cur < t["strong"]:
        zone = "中級反彈區(0.5~0.618)"
    elif cur < hi:
        zone = "強勢反彈區(>0.618,逼近回升)"
    else:
        zone = "已破前高=回升(趨勢反轉)"
    return {"high": round(hi, 1), "low": round(lo, 1), "current": round(cur, 1),
            "drop": round(drop, 1), "weak": t["weak"], "mid": t["mid"], "strong": t["strong"], "zone": zone}


def sr_levels(df, top=4):
    """支撐壓力線(SenVision find_support_resistance)。回 {'resistance':[...], 'support':[...]}。"""
    try:
        import sys
        sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
        from src.senvision.support_resistance import find_support_resistance
    except Exception:
        return {"resistance": [], "support": []}
    if df is None or len(df) < 30:
        return {"resistance": [], "support": []}
    lv = find_support_resistance(df[["high", "low", "close"]].reset_index(drop=True))
    res = sorted([l for l in lv if l.type == "resistance"], key=lambda l: l.price)[:top]
    sup = sorted([l for l in lv if l.type == "support"], key=lambda l: -l.price)[:top]
    f = lambda l: {"price": l.price, "strength": l.strength, "touches": l.touches}
    return {"resistance": [f(l) for l in res], "support": [f(l) for l in sup]}


def neckline_ctx(symbol):
    """讀最新 scan_auto CSV,取該股評分最高的蔡森型態(頸線/目標/狀態/方向)。無則 None。
    與 dailypicks 技術委員同一真相源(SenVision 多時框掃描,含週線)。"""
    try:
        files = sorted(glob.glob(os.path.join(_SCAN_DIR, "scan_auto_*.csv")), reverse=True)
        if not files:
            return None
        best = None
        with open(files[0], encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("股票代碼") or "").strip() != symbol:
                    continue
                try:
                    sc = float(r.get("評分") or 0)
                except ValueError:
                    sc = 0.0
                if best is None or sc > best["score"]:
                    nk = float(r.get("頸線") or 0)
                    tg = float(r.get("目標價") or 0)
                    best = {"pattern": r.get("形態", ""), "tf": r.get("時框", ""),
                            "status": r.get("狀態", ""), "neckline": round(nk, 2),
                            "target": round(tg, 2), "rrr": r.get("風報比", ""),
                            "score": sc, "dir": "bull" if tg >= nk else "bear"}
        return best
    except Exception:
        return None


def tech_signal(fib, sr, near=0.04, pattern=None):
    """技術訊號(規則式):蔡森型態頸線 → 現價 vs 支撐壓力線 + fib 反彈位置 → 一個標籤。
    回 (label, emoji, tone)。near=貼近門檻(預設4%)。pattern=neckline_ctx() 結果(可選)。"""
    if not fib:
        return ("—", "", "")
    cur, hi, lo = fib["current"], fib["high"], fib["low"]
    # ── 頸線(蔡森型態,最高優先:結構性突破/跌破)──
    if pattern and pattern.get("neckline"):
        nk = float(pattern["neckline"])
        tag = f"{pattern.get('tf', '')}{pattern.get('pattern', '型態')}".strip()
        stt = pattern.get("status", "")
        bull = pattern.get("dir") == "bull"
        if "突破" in stt:  # 剛突破(CSV 隔夜;加現價側別防呆,避免行情反轉後仍報假突破)
            if bull and cur >= nk * 0.98:
                return (f"突破頸線{nk:.0f}·{tag}", "🚀", "bull")
            if (not bull) and cur <= nk * 1.02:
                return (f"跌破頸線{nk:.0f}·{tag}", "🔻", "bear")
        if nk and abs(cur / nk - 1) <= near * 1.5:  # 成型中且逼近頸線 → 待表態
            return (f"逼近頸線{nk:.0f}{'待突破' if bull else '防跌破'}·{tag}", "🟠", "warn")
    res = sr.get("resistance", []) if sr else []   # 上方壓力,由近到遠
    sup = sr.get("support", []) if sr else []       # 下方支撐,由近到遠
    nr = res[0] if res else None
    ns = sup[0] if sup else None
    st = lambda x: "強" if x == "strong" else ("中" if x == "moderate" else "")
    # 優先序:回升 → 逼近壓力 → 測試支撐 → 築底/破底 → 反彈區 → 中性
    if cur >= hi * 0.999 or "回升" in fib["zone"]:
        return ("突破前高·回升", "🚀", "bull")
    if nr and nr["price"] and cur <= nr["price"] and (nr["price"] / cur - 1) <= near:
        return (f"逼近{st(nr['strength'])}壓力{nr['price']:.0f}", "🟠", "warn")
    if ns and ns["price"] and cur >= ns["price"] and (cur / ns["price"] - 1) <= near * 0.75:
        return (f"測試{st(ns['strength'])}支撐{ns['price']:.0f}", "🟡", "warn")
    if "仍在低點" in fib["zone"] or cur <= lo * 1.02:
        return ("築底/破底觀察", "🔻", "bear")
    z = fib["zone"]
    if "強勢反彈" in z:
        return ("強勢反彈·逼近回升", "📈", "bull")
    if "中級反彈" in z:
        return ("中級反彈中", "📈", "bull")
    if "弱勢反彈" in z:
        return ("弱勢反彈中", "📈", "")
    if "反彈初起" in z:
        return ("反彈初起", "📈", "")
    return ("趨勢中性", "", "")


def confluence(fib, sr, tol=0.02):
    """標記 fib 目標與支撐壓力線共振(價差 <tol)。回 {fib_key: 共振的線價}。"""
    if not fib or not sr:
        return {}
    out = {}
    levels = [x["price"] for x in sr.get("resistance", []) + sr.get("support", [])]
    for k in ("weak", "mid", "strong"):
        for lp in levels:
            if lp and abs(fib[k] / lp - 1) < tol:
                out[k] = lp
                break
    return out


def trapped_volume_zones(df, cur=None, top=3, mult=1.8, tol=0.03):
    """套牢量壓力區:下跌途中的爆量K棒(量>=20日均量×mult)且價位在現價上方 = 未來反彈解套賣壓。
    回 [{price, volume, dist%}] 由近到遠。跌深股反彈判讀第3點(蔡森/口訣:出量位置=日後壓力區)。"""
    if df is None or len(df) < 25 or "volume" not in df:
        return []
    cur = cur or float(df["close"].iloc[-1])
    v = df["volume"].astype(float)
    vma = v.rolling(20, min_periods=10).mean()
    cand = []
    for i in range(len(df)):
        m = vma.iloc[i]
        if m and v.iloc[i] >= m * mult:
            price = float((df["high"].iloc[i] + df["low"].iloc[i] + df["close"].iloc[i]) / 3)
            if price > cur * 1.005:                      # 只取現價上方=套牢壓力
                cand.append((price, float(v.iloc[i])))
    if not cand:
        return []
    cand.sort()
    zones = []
    for price, vol in cand:
        if zones and abs(price / zones[-1]["price"] - 1) <= tol:
            z = zones[-1]
            z["price"] = (z["price"] * z["n"] + price) / (z["n"] + 1)
            z["volume"] += vol
            z["n"] += 1
        else:
            zones.append({"price": price, "volume": vol, "n": 1})
    zones.sort(key=lambda z: -z["volume"])
    zones = zones[:top]
    zones.sort(key=lambda z: z["price"])
    return [{"price": round(z["price"], 2), "volume": z["volume"],
             "dist%": round((z["price"] / cur - 1) * 100, 1)} for z in zones]


def rebound_potential(db, symbol):
    """跌深反彈潛力(綜合跌深股自救寶典 3-6點):跌深+低檔出量+法人買超+距套牢量壓力空間。回 dict 或 None。"""
    df = price_series(db, symbol, 200)
    if df.empty or len(df) < 60 or "volume" not in df:
        return None
    fib = fib_rebound(df)
    if not fib:
        return None
    cur = fib["current"]
    drop = (cur / fib["high"] - 1) * 100
    v = df["volume"].astype(float)
    vol5 = float(v.iloc[-5:].mean()); vol60 = float(v.iloc[-60:].mean())
    low_vol_pickup = cur <= fib["low"] * 1.10 and vol60 and vol5 >= vol60 * 1.2
    inst = list(db.institutional_flow.find({"stock_id": symbol}, {"foreign_net": 1}).sort("date", -1).limit(10))
    fnet = sum((_g(x.get("foreign_net")) or 0) for x in inst) / 1000.0
    tz = trapped_volume_zones(df, cur)
    space = tz[0]["dist%"] if tz else None
    score, reasons = 0, []
    if drop <= -18:
        score += 1; reasons.append(f"跌深{drop:.0f}%")
    if low_vol_pickup:
        score += 2; reasons.append("低檔出量(近5日量放大)")
    if fnet > 0:
        score += 1; reasons.append(f"外資近10日買超{fnet:+.0f}張")
    elif fnet < 0:
        score -= 1; reasons.append(f"外資賣超{fnet:+.0f}張")
    if space is not None and space >= 8:
        score += 1; reasons.append(f"距套牢壓力{space:.0f}%有空間")
    elif space is not None and space < 3:
        reasons.append(f"貼近套牢壓力{space:.0f}%(空間小)")
    verdict = "反彈潛力高" if score >= 3 else ("反彈潛力中" if score >= 1 else "反彈動能不足")
    return {"verdict": verdict, "score": score, "reasons": reasons, "drop%": round(drop, 1),
            "fnet_10d": round(fnet), "trapped_resist": tz[0]["price"] if tz else None,
            "fib": {"weak": fib["weak"], "mid": fib["mid"], "strong": fib["strong"]}}
