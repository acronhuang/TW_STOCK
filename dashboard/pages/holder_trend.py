#!/usr/bin/env python3
"""個股股權分散趨勢

柱狀 — 總股東人數(total_holders)
折線 — 大股東持有率(big400_pct=>400張;可疊加 big_pct=>1000張千張)

資料源 shareholding(TDCC,每週一期),覆蓋 2023-03 起。可切 月/週/近50週。
欄位與 goodinfo 同源:big400_pct/big_pct/big_holders/total_holders 已驗證對得上。

render_trend(sid, kp) 抽成可複用 —— 大戶籌碼頁也 import 它做 drill-down。
"""
import bisect

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient

BULL = "#C2302C"
GREY = "#B8BEC8"


def _f(x):
    if x is None:
        return None
    try:
        return float(x.to_decimal()) if hasattr(x, "to_decimal") else float(x)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def stock_options():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    ids0 = [s for s in db.shareholding.distinct("stock_id")
            if len(s) == 4 and not s.startswith("00")]
    # 只留近1年有交易資料者(濾掉集保納入但無交易的標的:特別股/TDR/受益證券等,它們也無中文名)
    from datetime import timedelta as _td
    _lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
    if _lat:
        _tradable = set(db.stock_price.distinct("stock_id", {"date": {"$gte": _lat["date"] - _td(days=365)}}))
        ids = [s for s in ids0 if s in _tradable]
    else:
        ids = ids0
    names = {}
    # 只取「有名字」的最新一筆(近期價格列常缺 name 欄,原本 setdefault 會被空名蓋掉 → 1402 等顯示成空名)
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    # 補救:仍缺名者查 taiwan_stock_info
    missing = [s for s in ids if not names.get(s)]
    if missing:
        for r in db.taiwan_stock_info.find({"stock_id": {"$in": missing}},
                                           {"_id": 0, "stock_id": 1, "stock_name": 1}):
            if r.get("stock_name"):
                names[r["stock_id"]] = r["stock_name"]
    return sorted(ids), names


@st.cache_data(ttl=3600, show_spinner="載入股權分散…")
def load_trend(sid: str):
    """回傳原始每週資料(含 月/週 欄),聚合交給 _by_gran。"""
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    rows = list(db.shareholding.find(
        {"stock_id": sid},
        {"_id": 0, "date": 1, "big400_pct": 1, "big_pct": 1,
         "big_holders": 1, "total_holders": 1, "retail_pct": 1}
    ).sort("date", 1))
    if not rows:
        return pd.DataFrame()
    dates = [r["date"] for r in rows]
    px = {}
    for p in db.stock_price.find(
            {"stock_id": sid, "date": {"$gte": dates[0]}},
            {"_id": 0, "date": 1, "close": 1}).sort("date", 1):
        px[p["date"]] = _f(p.get("close"))
    px_dates = sorted(px)

    def close_on(d):
        i = bisect.bisect_right(px_dates, d) - 1
        return px[px_dates[i]] if i >= 0 else None

    for r in rows:
        r["收盤價"] = close_on(r["date"])
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["月"] = df["date"].dt.strftime("%Y-%m")
    df["週"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def _by_gran(df, gran):
    """依粒度回傳 (繪圖用 df, x 欄名)。
    月    — 每月最後一週(TDCC 每月 4~5 週,不聚合折線會鋸齒)
    週    — 原始每週一期
    近50週 — 最近 50 週
    """
    if gran == "月":
        return df.drop_duplicates("月", keep="last").reset_index(drop=True), "月"
    if gran == "近50週":
        return df.tail(50).reset_index(drop=True), "週"
    return df, "週"


def render_trend(sid: str, kp: str = ""):
    """畫某檔的股權分散趨勢(metrics + 雙軸圖 + 明細表)。kp = widget key 前綴,避免多處共用衝突。"""
    _, names = stock_options()
    df = load_trend(sid)
    if df.empty:
        st.warning(f"{sid} 沒有股權分散資料。")
        return

    c1, c2, c3 = st.columns([1.1, 1, 1])
    gran = c1.radio("週期", ["月", "週", "近50週"], horizontal=True, key=f"{kp}gran")
    tier = c2.radio("大股東持有率定義", [">400張", ">1000張(千張)"],
                    horizontal=True, key=f"{kp}tier")
    overlay = c3.checkbox("疊加另一級距", value=True, key=f"{kp}ov")
    field = "big400_pct" if tier == ">400張" else "big_pct"

    plot_df, xcol = _by_gran(df, gran)

    latest = df.iloc[-1]      # 指標永遠用最新一週
    k = st.columns(5)
    k[0].metric("總股東人數", f"{int(latest['total_holders']):,}")
    k[1].metric(">400張持有率", f"{latest['big400_pct']:.2f}%")
    k[2].metric(">1000張持有率", f"{latest['big_pct']:.2f}%")
    k[3].metric("千張大戶人數", f"{int(latest['big_holders']):,}")
    k[4].metric("收盤價", f"{latest['收盤價']:.2f}" if latest["收盤價"] else "—")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=plot_df[xcol], y=plot_df["total_holders"], name="總股東人數",
                         marker_color=GREY, opacity=0.75), secondary_y=False)
    fig.add_trace(go.Scatter(x=plot_df[xcol], y=plot_df[field], name=f"大股東持有率({tier})",
                             mode="lines+markers", line=dict(color=BULL, width=2)),
                  secondary_y=True)
    if overlay:
        other = "big_pct" if field == "big400_pct" else "big400_pct"
        olabel = ">1000張" if other == "big_pct" else ">400張"
        fig.add_trace(go.Scatter(x=plot_df[xcol], y=plot_df[other], name=f"({olabel})",
                                 mode="lines", line=dict(color="#D9A441", width=1.5, dash="dot")),
                      secondary_y=True)
    # 收盤價(第三軸,還原後):讓籌碼集中度與股價走勢直接對照
    if "收盤價" in plot_df.columns and plot_df["收盤價"].notna().any():
        fig.add_trace(go.Scatter(x=plot_df[xcol], y=plot_df["收盤價"], name="收盤價",
                                 mode="lines", line=dict(color="#1F77B4", width=1.6)))
        fig.data[-1].update(yaxis="y3")
    fig.update_yaxes(title_text="總股東人數", secondary_y=False)
    fig.update_yaxes(title_text="大股東持有率 %", secondary_y=True)
    fig.update_layout(height=440, margin=dict(l=0, r=0, t=30, b=0),
                      legend=dict(orientation="h", y=1.12), hovermode="x unified",
                      xaxis=dict(domain=[0.0, 0.93]),
                      yaxis3=dict(overlaying="y", side="right", position=0.99, anchor="free",
                                  title=dict(text="收盤價", font=dict(color="#1F77B4")),
                                  tickfont=dict(color="#1F77B4"), showgrid=False))
    st.plotly_chart(fig, use_container_width=True, key=f"{kp}chart")

    tbl = plot_df[[xcol, "total_holders", "big400_pct", "big_pct",
                   "big_holders", "retail_pct", "收盤價"]].copy()
    tbl.columns = ["資料期", "總股東人數", ">400張持有%", ">1000張持有%",
                   "千張大戶人數", "散戶持股%", "收盤價"]
    with st.expander(f"明細({gran},共 {len(plot_df)} 筆,可下載)"):
        st.dataframe(
            tbl.sort_values("資料期", ascending=False).style.format({
                "總股東人數": "{:,.0f}", ">400張持有%": "{:.2f}", ">1000張持有%": "{:.2f}",
                "千張大戶人數": "{:,.0f}", "散戶持股%": "{:.2f}", "收盤價": "{:.2f}",
            }, na_rep="—"),
            use_container_width=True, hide_index=True, height=340)
        st.download_button(
            "⬇️ 下載 CSV", tbl.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"holder_trend_{sid}_{gran}.csv", mime="text/csv", key=f"{kp}dl")

    st.caption(
        f"{sid} {names.get(sid, '')} 週資料 {len(df)} 期,{df['週'].iloc[0]} ~ {df['週'].iloc[-1]}。"
        "資料源 TDCC 每週一期;上方可切 月(每月最後一週)/ 週 / 近50週。"
        "⚠️ 尚未提供集保總張數、平均張數/人、各中間級距人數。")


def show():
    st.title("📊 個股股權分散趨勢")
    st.markdown("總股東人數(柱)與大股東持有率(折線)的歷史走勢 —— **股東數減少 + 持有率上升 = 籌碼集中**。")
    ids, names = stock_options()
    if not ids:
        st.error("shareholding 無資料。")
        return
    pre = st.session_state.get("drill_stock")
    default = ids.index(pre) if pre in ids else (ids.index("2330") if "2330" in ids else 0)
    sid = st.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    render_trend(sid, kp="pg_")
