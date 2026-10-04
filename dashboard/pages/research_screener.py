"""🔬 研究篩選 —— 全市場多因子綜合分 → 🟢🟡🔴 研究候選名單。

重用 StockRanker（value/quality/momentum/safety/institutional/growth 六維加權，
已剔除地雷股）。輸出為「研究名單」而非「買進名單」。門檻可於側邊欄調整。
"""
import sys

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.stock_ranker import StockRanker  # noqa: E402


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


@st.cache_data(ttl=1800, show_spinner="讀取因子最新日…")
def _factor_date():
    doc = _db().stock_factors.find_one({"date": {"$type": "date"}}, {"date": 1}, sort=[("date", -1)])
    return doc["date"] if doc else None


@st.cache_data(ttl=1800, show_spinner="跑全市場多因子評分…")
def _rank(limit):
    rows = StockRanker().rank(limit=limit, financial_check=True)
    out = []
    for r in rows:
        sc = r.get("scores", {})
        m = r.get("metrics", {})
        out.append({
            "代號": r["symbol"], "名稱": r.get("name", ""),
            "綜合分": r.get("total_score"), "評級": r.get("grade", ""),
            "估值": sc.get("value"), "品質": sc.get("quality"), "動能": sc.get("momentum"),
            "安全": sc.get("safety"), "籌碼": sc.get("institutional"), "成長": sc.get("growth"),
            "PE": m.get("pe_ratio"), "殖利率%": m.get("dividend_yield"),
            "ROE%": m.get("roe"), "RSI": m.get("rsi_14"),
        })
    return pd.DataFrame(out)


def _tier(score, green, red):
    if score is None:
        return "🟡"
    if score >= green:
        return "🟢"
    if score < red:
        return "🔴"
    return "🟡"


def show():
    st.title("🔬 研究篩選（全市場多因子）")
    st.caption("全市場 → 六維多因子綜合分（已剔除 TTM 虧損/高負債地雷股）→ 🟢🟡🔴 研究分級。"
               "**研究名單 ≠ 買進名單**；型態 ≠ 未來上漲；AI 篩選 ≠ 投資保證。")

    fdate = _factor_date()
    st.caption(f"因子資料日：**{str(fdate)[:10] if fdate else '—'}**")

    limit = st.sidebar.slider("評分檔數（取綜合分前 N）", 20, 200, 60, 10)
    green = st.sidebar.slider("🟢 門檻（綜合分 ≥）", 50, 90, 70, 1)
    red = st.sidebar.slider("🔴 門檻（綜合分 <）", 30, 60, 50, 1)
    if red > green:
        st.sidebar.warning("🔴 門檻不應高於 🟢 門檻")

    df = _rank(limit)
    if df.empty:
        st.warning("無評分結果 —— 可能 stock_factors 無資料或財報篩檢過嚴。")
        return

    df["分級"] = df["綜合分"].map(lambda s: _tier(s, green, red))

    fmt = {"綜合分": "{:.1f}", "估值": "{:.0f}", "品質": "{:.0f}", "動能": "{:.0f}",
           "安全": "{:.0f}", "籌碼": "{:.0f}", "成長": "{:.0f}", "PE": "{:.1f}",
           "殖利率%": "{:.2f}", "ROE%": "{:.1f}", "RSI": "{:.0f}"}
    cols = ["代號", "名稱", "綜合分", "評級", "估值", "品質", "動能", "安全", "籌碼",
            "成長", "PE", "殖利率%", "ROE%", "RSI"]

    counts = df["分級"].value_counts()
    k = st.columns(3)
    k[0].metric("🟢 值得深入研究", int(counts.get("🟢", 0)))
    k[1].metric("🟡 條件部分符合", int(counts.get("🟡", 0)))
    k[2].metric("🔴 暫不納入研究", int(counts.get("🔴", 0)))

    for tier, label in [("🟢", "值得深入研究"), ("🟡", "條件部分符合"), ("🔴", "暫不納入研究")]:
        sub = df[df["分級"] == tier]
        with st.expander(f"{tier} {label}（{len(sub)} 檔）", expanded=(tier == "🟢")):
            if sub.empty:
                st.caption("（無）")
            else:
                st.dataframe(sub[cols].style.format(fmt, na_rep="—"),
                             hide_index=True, width="stretch")

    st.download_button("⬇️ 下載研究名單 CSV",
                       df[["分級"] + cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"research_screen_{str(fdate)[:10]}.csv", mime="text/csv")
    st.caption("綜合分＝估值.25＋品質.20＋動能.15＋安全.15＋籌碼.15＋成長.10（各 0–100 百分位加權）。"
               "分級門檻可於側邊欄調整。本頁僅供研究起點，投資決策請自行確認。")
