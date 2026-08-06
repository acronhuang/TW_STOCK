"""📐 費波納契反彈 × 支撐壓力線 —— K線圖疊技術線 + 數據面板。

與 MoE 技術委員共用 src/analysis/tech_lines(同一真相源:原始價、自動 swing)。
"""
import sys
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.tech_lines import (  # noqa: E402
    price_series, fib_rebound, sr_levels, confluence, tech_signal, neckline_ctx,
    trapped_volume_zones, rebound_potential)

RES = "#E45756"   # 壓力紅
SUP = "#2E7D32"   # 支撐綠
FIB = "#D9A441"   # fib 金


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
    ids = sorted(s for s in db.stock_price.distinct(
        "stock_id", {"date": {"$gte": lat["date"] - timedelta(days=30)}})
        if len(s) == 4 and s.isdigit())
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    for r in db.taiwan_stock_info.find({"stock_id": {"$in": [s for s in ids if s not in names]}},
                                       {"_id": 0, "stock_id": 1, "stock_name": 1}):
        if r.get("stock_name"):
            names[r["stock_id"]] = r["stock_name"]
    return ids, names


def show():
    st.title("📐 費波納契反彈 × 支撐壓力線")
    st.caption("原始價、自動抓 swing(最高→之後最低);與 AI 技術委員共用同一計算。**金線=費波納契反彈目標,紅=壓力,綠=支撐**(線粗=強度)。")
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    ids, names = _stock_list()
    if not ids:
        st.error("無股價資料"); return
    c1, c2 = st.columns([3, 1])
    default = ids.index("2327") if "2327" in ids else 0
    sid = c1.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    lookback = c2.select_slider("回看天數", [120, 180, 250, 365], value=180)

    df = price_series(db, sid, lookback)
    if df.empty or len(df) < 20:
        st.warning("資料不足"); return
    fib = fib_rebound(df)
    sr = sr_levels(df)
    conf = confluence(fib, sr) if fib else {}

    # ── 指標卡 ──
    if fib:
        k = st.columns(5)
        k[0].metric("波段高", f"{fib['high']:.1f}")
        k[1].metric("波段低", f"{fib['low']:.1f}")
        k[2].metric("現價", f"{fib['current']:.1f}")
        k[3].metric("跌幅", f"{fib['drop']:.1f}")
        k[4].metric("現況", fib["zone"].split("(")[0])

    # ── 技術訊號(規則式自動標籤,與 MoE 技術委員共用 tech_signal;含蔡森頸線)──
    pat = neckline_ctx(sid)
    lbl, emj, tone = tech_signal(fib, sr, pattern=pat)
    if lbl and lbl != "—":
        det = ""
        if conf:
            det = "　⚡ Fib 目標與" + "、".join(
                {"weak": "弱勢", "mid": "中級", "strong": "強勢"}[kk] for kk in conf) + "反彈位有支撐壓力共振(更強關卡)"
        box = {"bull": st.success, "bear": st.error, "warn": st.warning}.get(tone, st.info)
        box(f"技術訊號:{emj} **{lbl}**{det}")
    rp = rebound_potential(db, sid)
    if rp:
        _t = "bull" if rp["score"] >= 3 else ("warn" if rp["score"] >= 1 else "bear")
        _b = {"bull": st.success, "warn": st.warning, "bear": st.error}.get(_t, st.info)
        _tr = f"、套牢量壓力{rp['trapped_resist']:.0f}" if rp["trapped_resist"] else ""
        _b(f"跌深反彈潛力:**{rp['verdict']}**(跌幅{rp['drop%']:+.0f}%{_tr}) —— {chr(0x3002).join(rp['reasons'][:3])}")
    if pat:
        st.caption(f"🔷 蔡森型態:{pat['tf']}{pat['pattern']} · {pat['status']} · "
                   f"頸線 {pat['neckline']:.2f} → 目標 {pat['target']:.2f}(風報比 {pat['rrr']}) "
                   f"〔{'多方' if pat['dir'] == 'bull' else '空方'}〕")

    # ── K線圖 + 疊線 ──
    fig = go.Figure(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K線", increasing_line_color="#E45756", decreasing_line_color="#2E7D32"))
    if fib:
        for key, lbl, k618 in [("weak", "弱勢0.382", fib["weak"]), ("mid", "中級0.5", fib["mid"]),
                               ("strong", "強勢0.618", fib["strong"])]:
            mark = " ⚡共振" if key in conf else ""
            fig.add_hline(y=k618, line=dict(color=FIB, width=1.5, dash="dash"),
                          annotation_text=f"{lbl} {k618:.0f}{mark}", annotation_position="right")
        fig.add_hline(y=fib["high"], line=dict(color="#9DA8B6", width=1, dash="dot"),
                      annotation_text=f"前高 {fib['high']:.0f}", annotation_position="right")
    for r in sr.get("resistance", []):
        w = {"strong": 2.5, "moderate": 1.5, "weak": 0.8}.get(r["strength"], 1)
        fig.add_hline(y=r["price"], line=dict(color=RES, width=w),
                      annotation_text=f"壓{r['price']:.0f}({r['touches']}觸)", annotation_position="left")
    for r in sr.get("support", []):
        w = {"strong": 2.5, "moderate": 1.5, "weak": 0.8}.get(r["strength"], 1)
        fig.add_hline(y=r["price"], line=dict(color=SUP, width=w),
                      annotation_text=f"撐{r['price']:.0f}({r['touches']}觸)", annotation_position="left")
    for z in trapped_volume_zones(df, fib["current"] if fib else None):
        fig.add_hline(y=z["price"], line=dict(color="#8E44AD", width=1.4, dash="dashdot"),
                      annotation_text=f"套牢量壓{z['price']:.0f}(+{z['dist%']:.0f}%)", annotation_position="right")
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # ── 數據面板 ──
    cc = st.columns(2)
    with cc[0]:
        st.markdown("**費波納契反彈目標**")
        if fib:
            rows = [{"強度": "弱勢 ×0.382", "目標價": fib["weak"], "共振": "⚡" if "weak" in conf else ""},
                    {"強度": "中級 ×0.5", "目標價": fib["mid"], "共振": "⚡" if "mid" in conf else ""},
                    {"強度": "強勢 ×0.618", "目標價": fib["strong"], "共振": "⚡" if "strong" in conf else ""}]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption("⚡ = 該反彈目標與支撐壓力線共振(價差 <2%),是更強的關卡。破強勢頂再上 = 回升(趨勢反轉)。")
    with cc[1]:
        st.markdown("**支撐壓力線(強度/觸碰)**")
        srrows = ([{"類型": "壓力", "價位": r["price"], "強度": r["strength"], "觸碰": r["touches"]}
                   for r in sr.get("resistance", [])] +
                  [{"類型": "支撐", "價位": r["price"], "強度": r["strength"], "觸碰": r["touches"]}
                   for r in sr.get("support", [])])
        if srrows:
            st.dataframe(pd.DataFrame(srrows), hide_index=True, use_container_width=True)
