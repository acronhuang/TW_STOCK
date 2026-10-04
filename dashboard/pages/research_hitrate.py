"""📈 研究名單命中率回看 —— 追蹤每日 🟢 研究名單的事後前瞻報酬與命中率。

資料來源：results/research_screen_*.json（由 scripts/screen_research.py 每日產出）。
前瞻報酬以 stock_price.adj_close 自名單日往後 N 個交易日計算。非投資建議，僅供研究驗證。
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
        greens = [(r["symbol"], r.get("name", "")) for r in d.get("rows", []) if r.get("tier") == "🟢"]
        recs.append({"date": d.get("data_date", os.path.basename(f)[16:26]), "symbols": greens})
    return recs


@st.cache_data(ttl=1800, show_spinner="計算前瞻報酬…")
def _fwd_returns(date_str, symbols, horizon):
    db = _db()
    try:
        entry = datetime.fromisoformat(date_str)
    except ValueError:
        return []
    out = []
    for sym, name in symbols:
        rows = list(db.stock_price.find(
            {"stock_id": sym, "date": {"$gte": entry, "$type": "date"}},
            {"date": 1, "adj_close": 1, "close": 1}).sort("date", 1).limit(horizon + 1))
        if len(rows) < horizon + 1:
            continue
        p0 = _g(rows[0].get("adj_close")) or _g(rows[0].get("close"))
        ph = _g(rows[horizon].get("adj_close")) or _g(rows[horizon].get("close"))
        if p0 and ph:
            out.append({"symbol": sym, "name": name, "ret": (ph / p0 - 1) * 100})
    return out


def show():
    st.title("📈 研究名單命中率回看")
    st.caption("追蹤每日 🟢 研究名單的事後前瞻報酬與命中率（報酬 > 0 的比例）。"
               "前瞻報酬需等名單日後累積足夠交易日才可評估。**非投資建議，僅供研究驗證。**")

    picks = _load_picks()
    if not picks:
        st.info("尚無研究名單歷史（results/research_screen_*.json）。"
                "排程每日 21:40 產出後，本頁會逐步累積可回看的資料。")
        return

    horizon = st.sidebar.selectbox("前瞻交易日", [5, 10, 20], index=1)

    rows, all_rets = [], []
    for p in picks:
        fwd = _fwd_returns(p["date"], tuple(p["symbols"]), horizon)
        rets = [x["ret"] for x in fwd]
        all_rets.extend(rets)
        rows.append({
            "名單日": p["date"], "🟢檔數": len(p["symbols"]), "可評估": len(rets),
            "平均報酬%": (sum(rets) / len(rets)) if rets else None,
            "命中率%": (100 * sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
        })
    df = pd.DataFrame(rows)

    k = st.columns(4)
    k[0].metric("名單天數", len(df))
    k[1].metric("可評估樣本", int(df["可評估"].sum()))
    k[2].metric(f"整體平均報酬%（{horizon}日）",
                f"{sum(all_rets) / len(all_rets):.2f}" if all_rets else "—")
    k[3].metric(f"整體命中率%（{horizon}日）",
                f"{100 * sum(1 for r in all_rets if r > 0) / len(all_rets):.1f}" if all_rets else "—")

    if not all_rets:
        st.warning(f"目前沒有任何名單已累積滿 {horizon} 個交易日，暫無法評估前瞻報酬。"
                   "請待交易日累積，或改選較短的前瞻天數。")

    st.dataframe(
        df.style.format({"平均報酬%": "{:+.2f}", "命中率%": "{:.1f}"}, na_rep="—"),
        hide_index=True, width="stretch")

    ev = df[df["可評估"] > 0]
    if len(ev) >= 2:
        st.markdown("### 命中率 / 平均報酬 趨勢")
        st.line_chart(ev.set_index("名單日")[["命中率%", "平均報酬%"]])

    st.caption("前瞻報酬＝名單日 adj_close 到其後第 N 個交易日 adj_close 的變動；命中＝報酬 > 0。"
               "樣本僅涵蓋名單日後已有足夠交易日者。研究名單 ≠ 買進名單。")
