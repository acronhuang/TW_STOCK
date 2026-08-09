"""📑 財報深度分析 —— 三率趨勢 / 三大現金流 / 負債結構,逐季(季報/半年報/年報)。

用回填的財報明細三表(financial_statement_detail/balance_sheet_detail/cash_flows_detail)。
與基本面委員共用 src/analysis/financial_statements。損益=單季、現金流=累計已差分成單季。
"""
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.financial_statements import quarterly_financials, REPORT, yoy_pct  # noqa: E402

YI = 1e8


def _num(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = _db()
    ids = sorted(db.financial_statement_detail.distinct("stock_id"))
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    return ids, names


@st.cache_data(ttl=1800, show_spinner=False)
def _data(sid, n):
    return quarterly_financials(_db(), sid, n)


def _single():
    ids, names = _stock_list()
    if not ids:
        st.error("無財報明細資料"); return
    c1, c2 = st.columns([3, 1])
    default = ids.index("2330") if "2330" in ids else 0
    sid = c1.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    nq = c2.select_slider("回看季數", [4, 8, 12, 20], value=12)

    rows = _data(sid, nq)
    if not rows:
        st.warning("該股無財報明細"); return
    df = pd.DataFrame(rows)
    cur = rows[-1]

    st.markdown(f"#### {sid} {names.get(sid, '')} — 最新 {cur['label']}（{cur['report']}）")
    k = st.columns(6)
    def m(col, lbl, v, suf="%", d=None):
        col.metric(lbl, f"{v:.1f}{suf}" if v is not None else "—", d)
    m(k[0], "毛利率", cur["gross_margin"])
    m(k[1], "營益率", cur["op_margin"])
    m(k[2], "淨利率", cur["net_margin"])
    k[3].metric("EPS(元)", f"{cur['eps']:.2f}" if cur["eps"] is not None else "—",
                f"YoY {cur['eps_yoy']:+.1f}%" if cur["eps_yoy"] is not None else None)
    k[4].metric("營運現金流/淨利", f"{cur['ocf_to_ni']*100:.0f}%" if cur["ocf_to_ni"] is not None else "—",
                help="現金含金量;>100%=賺的是真金白銀")
    m(k[5], "負債比", cur["debt_ratio"])
    k2 = st.columns(3)
    k2[0].metric("營運現金流(億)", f"{cur['ocf']/YI:,.0f}" if cur["ocf"] is not None else "—")
    k2[1].metric("自由現金流(億)", f"{cur['free_cf']/YI:,.0f}" if cur["free_cf"] is not None else "—", help="營運現金流−資本支出(CapEx)")
    k2[2].metric("應收週轉(天)", f"{cur['dso']:.1f}" if cur["dso"] is not None else "—", help="應收帳款收現天數,越低=收款越快、現金品質越好")

    # ── 三率趨勢 ──
    st.markdown("##### 📈 三率趨勢(獲利能力)")
    fig = go.Figure()
    for key, nm2, cr in [("gross_margin", "毛利率", "#4C78A8"), ("op_margin", "營益率", "#E45756"),
                         ("net_margin", "淨利率", "#2E7D32")]:
        fig.add_trace(go.Scatter(x=df["label"], y=df[key], name=nm2, mode="lines+markers",
                                 line=dict(width=2, color=cr)))
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=8, b=0), yaxis_title="%",
                      legend=dict(orientation="h", y=1.15))
    st.plotly_chart(fig, width='stretch')

    # ── 三大現金流(單季,億)──
    st.markdown("##### 💵 三大活動現金流(單季,億)")
    cfd = df.assign(營運=df["ocf"] / YI, 投資=df["icf"] / YI, 籌資=df["fcf"] / YI)
    fig2 = go.Figure()
    for nm2, cr in [("營運", "#2E7D32"), ("投資", "#4C78A8"), ("籌資", "#D9A441")]:
        fig2.add_trace(go.Bar(x=cfd["label"], y=cfd[nm2], name=nm2, marker_color=cr))
    fig2.add_hline(y=0, line=dict(color="#999", width=1))
    fig2.update_layout(height=300, margin=dict(l=0, r=0, t=8, b=0), barmode="group",
                       yaxis_title="億", legend=dict(orientation="h", y=1.15))
    st.plotly_chart(fig2, width='stretch')
    st.caption("營運>0 且投資<0(擴產)+籌資<0(還債/配息)= 健康的成熟企業現金流結構。")

    # ── 逐季明細表 ──
    st.markdown("##### 📋 逐季明細(報別 / 三率 / EPS / 現金流 / 負債)")
    show_df = pd.DataFrame([{
        "季別": r["label"], "報別": r["report"],
        "營收(億)": r["revenue"] / YI if r["revenue"] else None,
        "營收YoY%": r["revenue_yoy"], "毛利率%": r["gross_margin"], "營益率%": r["op_margin"],
        "淨利率%": r["net_margin"], "EPS": r["eps"], "EPS YoY%": r["eps_yoy"],
        "營運現金流(億)": r["ocf"] / YI if r["ocf"] is not None else None,
        "自由現金流(億)": r["free_cf"] / YI if r["free_cf"] is not None else None,
        "應收週轉(天)": r["dso"],
        "現金含金量%": r["ocf_to_ni"] * 100 if r["ocf_to_ni"] is not None else None,
        "負債比%": r["debt_ratio"], "流動比%": r["current_ratio"],
    } for r in reversed(rows)])
    st.dataframe(
        show_df.style
        .map(lambda v: f"color:{'#C62F35' if (pd.notna(v) and v<0) else '#1F8A54' if (pd.notna(v) and v>0) else ''}",
             subset=["營收YoY%", "EPS YoY%"])
        .format({"營收(億)": "{:,.1f}", "營收YoY%": "{:+.1f}", "毛利率%": "{:.1f}", "營益率%": "{:.1f}",
                 "淨利率%": "{:.1f}", "EPS": "{:.2f}", "EPS YoY%": "{:+.1f}", "營運現金流(億)": "{:,.1f}", "自由現金流(億)": "{:,.1f}", "應收週轉(天)": "{:.1f}",
                 "現金含金量%": "{:.0f}", "負債比%": "{:.1f}", "流動比%": "{:.0f}"}, na_rep="—"),
        hide_index=True, width='stretch', height=440)
    st.download_button("⬇️ 下載 CSV", show_df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"financials_deep_{sid}.csv", mime="text/csv")


@st.cache_data(ttl=1800, show_spinner="讀取全市場財報…")
def _market_rank():
    db = _db()
    dates = sorted(db.financial_statement_detail.distinct("date", {"type": "Revenue"}), reverse=True)
    ref = next((d for d in dates
                if db.financial_statement_detail.count_documents({"date": d, "type": "Revenue"}) >= 500),
               dates[0] if dates else None)
    if ref is None:
        return None, pd.DataFrame()
    prev = datetime(ref.year - 1, ref.month, ref.day)
    TYPES = ["Revenue", "GrossProfit", "IncomeAfterTaxes", "EPS"]

    def load(d):
        m = defaultdict(dict)
        for r in db.financial_statement_detail.find(
                {"date": d, "type": {"$in": TYPES}}, {"stock_id": 1, "type": 1, "value": 1}):
            m[r["stock_id"]][r["type"]] = _num(r["value"])
        return m
    cur, ly = load(ref), load(prev)
    season = {3: 1, 6: 2, 9: 3, 12: 4}[ref.month]
    PREVQ = {6: (3, 31), 9: (6, 30), 12: (9, 30)}

    def load_cf(d):
        m = defaultdict(dict)
        for r in db.cash_flows_detail.find(
                {"date": d, "type": {"$in": ["CashFlowsFromOperatingActivities", "PropertyAndPlantAndEquipment"]}},
                {"stock_id": 1, "type": 1, "value": 1}):
            m[r["stock_id"]][r["type"]] = _num(r["value"])
        return m
    cf_ref = load_cf(ref)
    cf_prev = load_cf(datetime(ref.year, *PREVQ[ref.month])) if season != 1 else {}
    ar_ref = {r["stock_id"]: _num(r["value"]) for r in db.balance_sheet_detail.find(
        {"date": ref, "type": "AccountsReceivableNet"}, {"stock_id": 1, "value": 1})}
    ids = [s for s in cur if len(s) == 4 and s.isdigit()]
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    rows = []
    for sid in ids:
        c = cur[sid]; l = ly.get(sid, {})
        rev = c.get("Revenue"); gp = c.get("GrossProfit"); ni = c.get("IncomeAfterTaxes"); eps = c.get("EPS")
        if not rev:
            continue
        _cf = cf_ref.get(sid, {})
        ocf = _cf.get("CashFlowsFromOperatingActivities"); capex = _cf.get("PropertyAndPlantAndEquipment")
        if season != 1:
            _p = cf_prev.get(sid, {})
            _po = _p.get("CashFlowsFromOperatingActivities"); _pc = _p.get("PropertyAndPlantAndEquipment")
            ocf = (ocf - _po) if (ocf is not None and _po is not None) else None
            capex = (capex - _pc) if (capex is not None and _pc is not None) else None
        free_cf = (ocf + capex) if (ocf is not None and capex is not None) else None
        _ar = ar_ref.get(sid)
        dso = (_ar / rev * 91.25) if (_ar and rev) else None
        rows.append({
            "代號": sid, "名稱": names.get(sid, ""),
            "營收(億)": round(rev / YI, 1),
            "獲利(億)": round(ni / YI, 1) if ni is not None else None,
            "EPS": eps,
            "毛利率%": round(gp / rev * 100, 1) if gp is not None else None,
            "自由現金流(億)": round(free_cf / YI, 1) if free_cf is not None else None,
            "應收週轉(天)": round(dso, 1) if dso is not None else None,
            "營收YoY%": (lambda v: round(v, 1) if v is not None else None)(yoy_pct(rev, l.get("Revenue"))),
            "獲利YoY%": (lambda v: round(v, 1) if v is not None else None)(yoy_pct(ni, l.get("IncomeAfterTaxes"))),
            "EPS YoY%": (lambda v: round(v, 1) if v is not None else None)(yoy_pct(eps, l.get("EPS"))),
            "去年同季轉機": ("虧轉盈" if (l.get("IncomeAfterTaxes") is not None and l["IncomeAfterTaxes"] <= 0 and ni is not None and ni > 0)
                       else ("盈轉虧" if (l.get("IncomeAfterTaxes", 0) or 0) > 0 and ni is not None and ni <= 0
                             else ("續虧" if (ni is not None and ni <= 0) else ""))),
        })
    m = {3: 1, 6: 2, 9: 3, 12: 4}[ref.month]
    return f"{ref.year}Q{m}（{REPORT[m]}）", pd.DataFrame(rows)


def _market():
    label, df = _market_rank()
    if df is None or df.empty:
        st.info("無全市場財報資料"); return
    st.caption(f"財報季別:**{label}** · 共 {len(df):,} 檔(同季 YoY 比去年同季)")
    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("搜尋代號/名稱", "", key="fin_mkt_q")
    sortby = c2.selectbox("排序", ["EPS", "獲利YoY%", "營收YoY%", "毛利率%", "自由現金流(億)", "應收週轉(天)", "EPS YoY%", "營收(億)", "獲利(億)"])
    min_rev = c3.select_slider("最低營收(億)", [0, 1, 5, 10, 50], value=1)
    view = df.copy()
    if min_rev:
        view = view[view["營收(億)"].fillna(0) >= min_rev]
    if q.strip():
        s = q.strip().lower()
        view = view[view["代號"].str.lower().str.contains(s) | view["名稱"].str.lower().str.contains(s)]
    quality = st.checkbox("🏅 品質快篩:自由現金流>0 · 應收週轉<60天 · 毛利率>20% · 獲利YoY>0(賺錢·收款快·有成長)",
                          value=False, key="fin_mkt_quality")
    if quality:
        view = view[(view["自由現金流(億)"] > 0) & (view["應收週轉(天)"] < 60)
                    & (view["毛利率%"] > 20) & (view["獲利YoY%"] > 0)]
    asc = st.checkbox("由小到大", value=False, key="fin_mkt_asc")
    view = view.sort_values(sortby, ascending=asc, na_position="last")
    st.caption(f"顯示 {len(view):,} / {len(df):,} 檔　排序:{sortby} {'↑' if asc else '↓'}")
    st.dataframe(
        view.style.map(lambda v: f"color:{'#C62F35' if (pd.notna(v) and v<0) else '#1F8A54' if (pd.notna(v) and v>0) else ''}",
                       subset=["營收YoY%", "獲利YoY%", "EPS YoY%"])
            .format({"營收(億)": "{:,.1f}", "獲利(億)": "{:,.1f}", "EPS": "{:.2f}", "毛利率%": "{:.1f}",
                     "營收YoY%": "{:+.1f}", "獲利YoY%": "{:+.1f}", "EPS YoY%": "{:+.1f}", "自由現金流(億)": "{:,.1f}", "應收週轉(天)": "{:.1f}"}, na_rep="—"),
        hide_index=True, width='stretch', height=560)
    st.download_button("⬇️ 下載 CSV", view.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"financial_rank_{label[:6]}.csv", mime="text/csv")
    st.caption("YoY 用 (今−去年)/**|去年|** 計算 → 虧轉盈=正、由盈轉虧=負(符號正確)。"
               "但去年同季基期**近零**時 YoY 仍會偏大,且『轉機』欄標示者是**負基期**的成長率,"
               "請搭配『去年同季轉機』欄 + 今EPS/獲利絕對值一起看。")


def show():
    st.title("📑 財報深度分析")
    st.caption("三率趨勢 / 三大現金流 / 負債結構(單股)+ 全市場財報榜。來源:財報明細三表;損益=單季、現金流已差分成單季。")
    t1, t2 = st.tabs(["📈 單股深度(逐季)", "🏆 全市場財報榜"])
    with t1:
        _single()
    with t2:
        _market()
