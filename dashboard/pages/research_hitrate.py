"""📈 研究名單命中率回看 —— 追蹤 🟢🟡🔴 研究名單的事後前瞻報酬與命中率。

資料來源：results/research_screen_*.json（scripts/screen_research.py 每日產出）。
進場方式可選「當日收盤」或「隔日開盤」；前瞻報酬以 adj_close/adj_open 計算。
分級對照可驗證 🟢 是否真的優於 🟡🔴。非投資建議，僅供研究驗證。
"""
import glob
import json
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st
from pymongo import MongoClient

RESULTS_DIR = "/home/mdsadmin/Stock/tw-stock-analysis/results"
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
TIERS = ["🟢", "🟡", "🔴"]


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=1800, show_spinner="讀研究名單歷史…")
def _load_picks():
    recs = []
    for f in sorted(glob.glob(os.path.join(RESULTS_DIR, "research_screen_*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        rows = [(r["symbol"], r.get("name", ""), r.get("tier", "🟡"))
                for r in d.get("rows", [])]
        recs.append({"date": d.get("data_date", os.path.basename(f)[16:26]), "rows": rows})
    return recs


@st.cache_data(ttl=1800, show_spinner="計算前瞻報酬…")
def _fwd_returns(date_str, rows, horizon, entry_mode):
    """entry_mode: 'close'=當日收盤進場; 'open'=隔日開盤進場。回 [{symbol,tier,ret}]。"""
    db = _db()
    try:
        entry = datetime.fromisoformat(date_str)
    except ValueError:
        return []
    need = horizon + (1 if entry_mode == "close" else 2)
    out = []
    for sym, name, tier in rows:
        px = list(db.stock_price.find(
            {"stock_id": sym, "date": {"$gte": entry, "$type": "date"}},
            {"adj_close": 1, "close": 1, "adj_open": 1, "open": 1}).sort("date", 1).limit(need))
        if len(px) < need:
            continue
        if entry_mode == "close":
            p0 = _g(px[0].get("adj_close")) or _g(px[0].get("close"))
            pn = _g(px[horizon].get("adj_close")) or _g(px[horizon].get("close"))
        else:
            p0 = _g(px[1].get("adj_open")) or _g(px[1].get("open"))
            pn = _g(px[horizon + 1].get("adj_close")) or _g(px[horizon + 1].get("close"))
        if p0 and pn:
            out.append({"symbol": sym, "tier": tier, "ret": (pn / p0 - 1) * 100})
    return out


def _agg(rets):
    if not rets:
        return None, None
    return sum(rets) / len(rets), 100 * sum(1 for r in rets if r > 0) / len(rets)


def show():
    st.title("📈 研究名單命中率回看")
    st.caption("追蹤每日 🟢🟡🔴 研究名單的事後前瞻報酬與命中率。可比對分級是否有效、"
               "及收盤/隔日開盤進場差異。**非投資建議，僅供研究驗證。**")

    picks = _load_picks()
    if not picks:
        st.info("尚無研究名單歷史（results/research_screen_*.json）。"
                "排程每日 21:40 產出後，本頁會逐步累積可回看的資料。")
        return

    horizon = st.sidebar.selectbox("前瞻交易日", [5, 10, 20], index=1)
    entry_label = st.sidebar.radio("進場方式", ["當日收盤", "隔日開盤"], horizontal=True)
    entry_mode = "close" if entry_label == "當日收盤" else "open"

    by_tier = {t: [] for t in TIERS}
    per_date = []
    for p in picks:
        fwd = _fwd_returns(p["date"], tuple(p["rows"]), horizon, entry_mode)
        for x in fwd:
            if x["tier"] in by_tier:
                by_tier[x["tier"]].append(x["ret"])
        g = [x["ret"] for x in fwd if x["tier"] == "🟢"]
        avg, hit = _agg(g)
        per_date.append({"名單日": p["date"],
                         "🟢檔數": sum(1 for r in p["rows"] if r[2] == "🟢"),
                         "🟢可評估": len(g), "🟢平均報酬%": avg, "🟢命中率%": hit})

    total_eval = sum(len(v) for v in by_tier.values())
    k = st.columns(4)
    k[0].metric("名單天數", len(picks))
    k[1].metric("可評估樣本", total_eval)
    k[2].metric("進場方式", entry_label)
    k[3].metric("前瞻", f"{horizon} 交易日")

    if total_eval == 0:
        st.warning(f"目前沒有任何名單已累積滿 {horizon}（含進場日）個交易日，暫無法評估。"
                   "請待交易日累積，或改選較短的前瞻天數。")
        return

    st.markdown("### 分級對照（驗證 🟢 是否優於 🟡🔴）")
    cmp_rows = []
    for t in TIERS:
        avg, hit = _agg(by_tier[t])
        cmp_rows.append({"分級": t, "可評估檔數": len(by_tier[t]),
                         "平均報酬%": avg, "命中率%": hit})
    st.dataframe(pd.DataFrame(cmp_rows).style.format(
        {"平均報酬%": "{:+.2f}", "命中率%": "{:.1f}"}, na_rep="—"),
        hide_index=True, width="stretch")
    st.caption("若分級有效，平均報酬與命中率應呈 🟢 > 🟡 > 🔴。")

    st.markdown("### 🟢 名單逐日表現")
    df = pd.DataFrame(per_date)
    st.dataframe(df.style.format({"🟢平均報酬%": "{:+.2f}", "🟢命中率%": "{:.1f}"}, na_rep="—"),
                 hide_index=True, width="stretch")
    ev = df[df["🟢可評估"] > 0]
    if len(ev) >= 2:
        st.line_chart(ev.set_index("名單日")[["🟢命中率%", "🟢平均報酬%"]])

    st.caption("前瞻報酬：當日收盤進場＝名單日 adj_close→第 N 交易日 adj_close；"
               "隔日開盤進場＝次一交易日 adj_open→其後第 N 交易日 adj_close。命中＝報酬 > 0。"
               "研究名單 ≠ 買進名單。")
