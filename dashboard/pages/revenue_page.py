"""📈 月營收 —— 單股月營收趨勢 + YoY/MoM 動能 + 全市場成長榜。

資料源 monthly_revenue(FinMind,單位千元;每月10日前公布上月)。與 MoE 基本面委員共用同一資料。
"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient

RED = "#E45756"
BLUE = "#4C78A8"


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
    except (TypeError, ValueError):
        return None


def _yi(v):  # 千元 → 億元
    return round(v / 1e5, 2) if v is not None else None


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = _db()
    ids, names = [], {}
    for r in db.monthly_revenue.aggregate([
        {"$group": {"_id": "$symbol", "name": {"$last": "$name"}}}]):
        s = r["_id"]
        if isinstance(s, str) and len(s) == 4 and s.isdigit():
            ids.append(s)
            names[s] = r.get("name") or ""
    return sorted(ids), names


@st.cache_data(ttl=1800, show_spinner=False)
def _latest_month():
    db = _db()
    d = db.monthly_revenue.find_one(sort=[("year_month", -1)])
    return d["year_month"] if d else None


def _single(db):
    ids, names = _stock_list()
    if not ids:
        st.error("無月營收資料"); return
    c1, c2 = st.columns([3, 1])
    default = ids.index("2330") if "2330" in ids else 0
    sid = c1.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    months = c2.select_slider("回看月數", [12, 24, 36, 60], value=24)

    rows = list(db.monthly_revenue.find({"symbol": sid}).sort("year_month", -1).limit(months))
    rows.reverse()
    if not rows:
        st.warning("該股無月營收"); return
    df = pd.DataFrame([{
        "月份": r.get("year_month"),
        "營收(億)": _yi(_f(r.get("revenue"))),
        "YoY%": round(_f(r.get("yoy_growth")), 1) if _f(r.get("yoy_growth")) is not None else None,
        "MoM%": round(_f(r.get("mom_growth")), 1) if _f(r.get("mom_growth")) is not None else None,
        "累計YoY%": round(_f(r.get("cumulative_growth")), 1) if _f(r.get("cumulative_growth")) is not None else None,
    } for r in rows])

    cur = df.iloc[-1]
    k = st.columns(4)
    k[0].metric(f"{cur['月份']} 營收(億)", f"{cur['營收(億)']:,.1f}" if cur["營收(億)"] is not None else "—")
    k[1].metric("YoY 年增", f"{cur['YoY%']:+.1f}%" if pd.notna(cur["YoY%"]) else "—")
    k[2].metric("MoM 月增", f"{cur['MoM%']:+.1f}%" if pd.notna(cur["MoM%"]) else "—")
    k[3].metric("累計 YoY", f"{cur['累計YoY%']:+.1f}%" if pd.notna(cur["累計YoY%"]) else "—")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["月份"], y=df["營收(億)"], name="月營收(億)", marker_color=BLUE, opacity=0.6),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["月份"], y=df["YoY%"], name="YoY 年增%", line=dict(color=RED, width=2), mode="lines+markers"),
                  secondary_y=True)
    fig.add_hline(y=0, line=dict(color="#999", width=1, dash="dot"), secondary_y=True)
    fig.update_layout(height=440, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(title_text="營收(億)", secondary_y=False)
    fig.update_yaxes(title_text="YoY %", secondary_y=True)
    st.plotly_chart(fig, width='stretch')

    st.markdown("**明細(近→遠)**")
    tbl = df.sort_values("月份", ascending=False)
    st.dataframe(tbl.style.format({"營收(億)": "{:,.1f}", "YoY%": "{:+.1f}", "MoM%": "{:+.1f}",
                                   "累計YoY%": "{:+.1f}"}, na_rep="—"),
                 hide_index=True, width='stretch', height=360)
    st.download_button("⬇️ 下載 CSV", tbl.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"revenue_{sid}.csv", mime="text/csv")


@st.cache_data(ttl=1800, show_spinner="讀取全市場…")
def _rank_data(month):
    db = _db()
    rows = []
    for r in db.monthly_revenue.find({"year_month": month}):
        s = r.get("symbol")
        if not (isinstance(s, str) and len(s) == 4 and s.isdigit()):
            continue
        rows.append({
            "代號": s, "名稱": r.get("name") or "", "產業": r.get("industry") or "",
            "營收(億)": _yi(_f(r.get("revenue"))),
            "YoY%": round(_f(r.get("yoy_growth")), 1) if _f(r.get("yoy_growth")) is not None else None,
            "MoM%": round(_f(r.get("mom_growth")), 1) if _f(r.get("mom_growth")) is not None else None,
            "累計YoY%": round(_f(r.get("cumulative_growth")), 1) if _f(r.get("cumulative_growth")) is not None else None,
        })
    return pd.DataFrame(rows)


def _ranking(db):
    month = _latest_month()
    if not month:
        st.error("無資料"); return
    st.caption(f"最新月份:**{month}**(每月約 10 日公布上月)。⚠️ 建設股/小型股基期近零時 YoY 會爆表(非真動能),"
               "用『最低營收』過濾掉小基期雜訊。")
    df = _rank_data(month)
    if df.empty:
        st.info("無資料"); return
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    q = c1.text_input("搜尋代號/名稱/產業", "")
    sortby = c2.selectbox("排序", ["YoY%", "MoM%", "累計YoY%", "營收(億)"])
    min_rev = c3.select_slider("最低營收(億)", [0, 1, 5, 10, 50, 100], value=5)
    asc = c4.checkbox("由小到大", value=False)
    ex_lumpy = st.checkbox("排除營建/投資控股(基期 lumpy,YoY 易失真)", value=True)
    view = df.copy()
    if ex_lumpy:
        view = view[view["產業"] != "建材營造"]
        view = view[~view["名稱"].str.contains("投資|建設|營建|開發", na=False)]
    if min_rev:
        view = view[view["營收(億)"].fillna(0) >= min_rev]
    if q.strip():
        s = q.strip().lower()
        view = view[view["代號"].str.lower().str.contains(s) | view["名稱"].str.lower().str.contains(s)
                    | view["產業"].str.lower().str.contains(s)]
    view = view.sort_values(sortby, ascending=asc, na_position="last")
    st.caption(f"顯示 {len(view):,} / {len(df):,} 檔　排序:{sortby} {'↑' if asc else '↓'}")
    st.dataframe(
        view.style.map(lambda v: f"color:{'#C62F35' if (pd.notna(v) and v > 0) else '#1F8A54' if (pd.notna(v) and v < 0) else ''}",
                       subset=["YoY%", "MoM%", "累計YoY%"])
            .format({"營收(億)": "{:,.1f}", "YoY%": "{:+.1f}", "MoM%": "{:+.1f}", "累計YoY%": "{:+.1f}"}, na_rep="—"),
        hide_index=True, width='stretch', height=520)
    st.download_button("⬇️ 下載 CSV", view.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"revenue_rank_{month}.csv", mime="text/csv")


def show():
    st.title("📈 月營收")
    st.caption("月營收趨勢與 YoY/MoM 動能。單位:億元(原始千元換算)。與 MoE 基本面委員共用同一 monthly_revenue。")
    db = _db()
    t1, t2 = st.tabs(["📊 單股趨勢", "🏆 全市場成長榜"])
    with t1:
        _single(db)
    with t2:
        _ranking(db)
