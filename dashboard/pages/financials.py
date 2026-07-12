#!/usr/bin/env python3
"""財報摘要儀表：讀 quarterly_earnings（實際財報表，涵蓋 ~1980 檔）。
取代原本讀 financial_reports（棄用舊表，僅 ~200 檔，多數股票查無資料）。"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient


@st.cache_resource
def _db():
    return MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _yi(v):
    """元 → 億（1e8），None 安全。"""
    n = _num(v)
    return round(n / 1e8, 2) if n is not None else None


def show():
    st.title("📑 財報摘要儀表")
    db = _db()

    name_map = {d["stock_id"]: d.get("stock_name", "")
                for d in db.taiwan_stock_info.find({}, {"stock_id": 1, "stock_name": 1})}

    sym = st.text_input("股票代碼", value="2330",
                        help="輸入代碼查該股季度財報，如 2330、6811").strip()
    if not sym:
        st.info("請輸入股票代碼。")
        return

    qs = list(db.quarterly_earnings.find({"symbol": sym}).sort([("year", 1), ("season", 1)]))
    if not qs:
        st.warning(f"⚠️ 查無 {sym} 的財報數據（quarterly_earnings）。"
                   f"該股可能非涵蓋範圍（本表約 1,980 檔上市櫃個股）。")
        return

    st.subheader(f"{sym} {name_map.get(sym, '')}　共 {len(qs)} 季")

    # ── 最新一季摘要 ──
    latest = qs[-1]
    inc = latest.get("income", {}) or {}
    bal = latest.get("balance", {}) or {}
    st.markdown(f"### 最新一季：{latest['year']} Q{latest['season']}")
    c = st.columns(5)
    c[0].metric("營收", f"{_yi(inc.get('revenue'))} 億" if _yi(inc.get('revenue')) is not None else "-")
    c[1].metric("EPS", f"{_num(inc.get('eps')):.2f}" if _num(inc.get('eps')) is not None else "-")
    c[2].metric("淨利率", f"{_num(inc.get('net_margin')):.2f}%" if _num(inc.get('net_margin')) is not None else "-")
    c[3].metric("營益率", f"{_num(inc.get('operating_margin')):.2f}%" if _num(inc.get('operating_margin')) is not None else "-")
    c[4].metric("ROE", f"{_num(bal.get('roe')):.2f}%" if _num(bal.get('roe')) is not None else "-")

    # ── 趨勢圖：營收(柱) + EPS(線) ──
    st.markdown("### 📈 營收與 EPS 趨勢")
    labels = [f"{q['year']}Q{q['season']}" for q in qs]
    rev = [_yi((q.get("income", {}) or {}).get("revenue")) for q in qs]
    eps = [_num((q.get("income", {}) or {}).get("eps")) for q in qs]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=labels, y=rev, name="營收(億)", marker_color="#8fbcd4"), secondary_y=False)
    fig.add_trace(go.Scatter(x=labels, y=eps, name="EPS(元)", line=dict(color="#d62728", width=2),
                             mode="lines+markers"), secondary_y=True)
    fig.update_layout(height=360, margin=dict(t=20, b=20), hovermode="x unified",
                      legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(title_text="營收(億)", secondary_y=False)
    fig.update_yaxes(title_text="EPS(元)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    # ── 逐季明細表 ──
    st.markdown("### 📋 逐季明細")
    rows = []
    for q in qs:
        i = q.get("income", {}) or {}
        b = q.get("balance", {}) or {}
        rows.append({
            "季別": f"{q['year']}Q{q['season']}",
            "營收(億)": _yi(i.get("revenue")),
            "營業利益(億)": _yi(i.get("operating_income")),
            "淨利(億)": _yi(i.get("net_income")),
            "EPS": _num(i.get("eps")),
            "營益率%": _num(i.get("operating_margin")),
            "淨利率%": _num(i.get("net_margin")),
            "ROE%": _num(b.get("roe")),
            "總資產(億)": _yi(b.get("total_assets")),
            "總負債(億)": _yi(b.get("total_liabilities")),
            "股東權益(億)": _yi(b.get("total_equity")),
        })
    df = pd.DataFrame(rows).iloc[::-1]  # 新到舊
    st.dataframe(df, width="stretch", hide_index=True, height=380)
    st.download_button("下載財報 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{sym}_financials.csv", mime="text/csv")
