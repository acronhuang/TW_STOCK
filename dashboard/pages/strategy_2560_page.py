"""🎯 2560戰法 —— 世界交易冠軍安德烈·布殊:MA25(25日均價線)向上 + K線踩25線起動 + 量能(5均量vs60均量)配合。

四情境:❌誘惑(無量放棄)/🟡衝量(短線)/✅做量(波段)/🎯縮量(黑馬)。與 MoE 技術委員共用 classify_2560。用還原價+成交量。
"""
import sys
from collections import defaultdict
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.strategy_2560 import classify_2560, _mean  # noqa: E402

SCEN_COLOR = {"縮量": "#C62F35", "做量": "#1F8A54", "衝量": "#B4841F", "誘惑": "#9DA8B6"}


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=1800, show_spinner="掃描全市場 2560…")
def _scan():
    db = _db()
    lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])["date"]
    start = lat - timedelta(days=150)
    ser, raws, names = defaultdict(list), defaultdict(list), {}
    for r in db.stock_price.find({"date": {"$gte": start, "$type": "date"}},
                                 {"stock_id": 1, "close": 1, "adj_close": 1, "volume": 1, "name": 1}
                                 ).sort([("stock_id", 1), ("date", 1)]):
        s = r["stock_id"]
        if not (len(s) == 4 and s.isdigit() and not s.startswith("00")):
            continue
        c = _g(r.get("adj_close")) or _g(r.get("close"))
        raw = _g(r.get("close"))
        v = _g(r.get("volume"))
        if c and v is not None:
            ser[s].append((c, v))
            raws[s].append(raw or c)
        if r.get("name"):
            names[s] = r["name"]
    rows = []
    for s, sv in ser.items():
        if len(sv) < 65:
            continue
        closes = [x[0] for x in sv]
        vols = [x[1] for x in sv]
        res = classify_2560(closes, vols)
        if not res or not res["setup"]:
            continue
        turnover = _mean([raws[s][i] * vols[i] for i in range(-20, 0)]) / 1e8 if len(raws[s]) >= 20 else None
        rows.append({
            "代號": s, "名稱": names.get(s, ""), "情境": f"{res['emoji']} {res['scenario']}",
            "判讀": res["label"], "收盤": raws[s][-1], "MA25(還原)": res["ma25"],
            "離25線%": res["dist%"], "量比(5/60)": res["vol5_60"],
            "日均額(億)": round(turnover, 2) if turnover is not None else None,
        })
    return str(lat)[:10], pd.DataFrame(rows)


def _market():
    date, df = _scan()
    if df.empty:
        st.info("目前無符合『踩25線起動』的股"); return
    st.caption(f"資料日 {date} · 全市場符合『MA25向上 + 踩25線起動』共 {len(df):,} 檔")
    counts = df["情境"].value_counts()
    st.caption("📊 情境分布:　" + "　·　".join(f"{k}×{v}" for k, v in counts.items()))

    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("搜尋代號/名稱", "", key="s2560_q")
    scen_opts = ["做量+縮量(優)", "全部"] + [s for s in ["🎯 縮量", "✅ 做量", "🟡 衝量", "❌ 誘惑"] if s in set(df["情境"])]
    pick = c2.selectbox("情境", scen_opts)
    amt = c3.select_slider("日均額下限(億)", [0, 0.5, 1, 3, 10], value=0.5)
    view = df.copy()
    if pick == "做量+縮量(優)":
        view = view[view["情境"].str.contains("做量|縮量")]
    elif pick != "全部":
        view = view[view["情境"] == pick]
    if amt:
        view = view[view["日均額(億)"].fillna(0) >= amt]
    if q.strip():
        s = q.strip().lower()
        view = view[view["代號"].str.lower().str.contains(s) | view["名稱"].str.lower().str.contains(s)]
    view = view.sort_values("量比(5/60)", ascending=False)
    st.caption(f"顯示 {len(view):,} / {len(df):,} 檔")

    def _c(v):
        for k, col in SCEN_COLOR.items():
            if isinstance(v, str) and k in v:
                return f"color:{col};font-weight:600"
        return ""
    st.dataframe(
        view.style.map(_c, subset=["情境"]).format(
            {"收盤": "{:.2f}", "MA25(還原)": "{:.2f}", "離25線%": "{:+.1f}", "量比(5/60)": "{:.2f}",
             "日均額(億)": "{:.2f}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=520)
    st.download_button("⬇️ 下載 CSV", view.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"strategy2560_{date}.csv", mime="text/csv")


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = _db()
    lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
    ids = sorted(s for s in db.stock_price.distinct("stock_id", {"date": {"$gte": lat["date"] - timedelta(days=20)}})
                 if len(s) == 4 and s.isdigit() and not s.startswith("00"))
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    return ids, names


def _single():
    ids, names = _stock_list()
    default = ids.index("2330") if "2330" in ids else 0
    sid = st.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    db = _db()
    lat = db.stock_price.find_one({"stock_id": sid, "date": {"$type": "date"}}, sort=[("date", -1)])
    if not lat:
        st.warning("無資料"); return
    rows = []
    for r in db.stock_price.find({"stock_id": sid, "date": {"$gte": lat["date"] - timedelta(days=200), "$type": "date"}},
                                 {"date": 1, "close": 1, "adj_close": 1, "volume": 1}).sort("date", 1):
        c = _g(r.get("adj_close")) or _g(r.get("close"))
        raw = _g(r.get("close"))
        v = _g(r.get("volume"))
        if c and v is not None:
            rows.append((r["date"], c, v, raw))
    if len(rows) < 65:
        st.warning("資料不足"); return
    closes = [x[1] for x in rows]
    vols = [x[2] for x in rows]
    res = classify_2560(closes, vols)
    box = {"bull": st.success, "warn": st.warning, "bear": st.error}.get(res["tone"], st.info)
    box(f"2560訊號:{res['emoji']} **{res['label']}**　"
        f"(MA25還原{res['ma25']} {'↑向上' if res['ma25_rising'] else '↓走平/向下'}、離25線{res['dist%']:+.1f}%、量比(5/60){res['vol5_60']})")

    df = pd.DataFrame(rows[-120:], columns=["date", "adj", "vol", "raw"])
    df["ma25"] = pd.Series([x[1] for x in rows]).rolling(25).mean().iloc[-120:].values
    df["v5"] = pd.Series(vols).rolling(5).mean().iloc[-120:].values
    df["v60"] = pd.Series(vols).rolling(60).mean().iloc[-120:].values
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=df["date"], y=df["adj"], name="還原價", line=dict(color="#4C78A8", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ma25"], name="MA25", line=dict(color="#D9A441", width=2)), row=1, col=1)
    fig.add_trace(go.Bar(x=df["date"], y=df["vol"], name="量", marker_color="#C9D3DF"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["v5"], name="5均量", line=dict(color="#E45756", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["v60"], name="60均量", line=dict(color="#2E7D32", width=1.5)), row=2, col=1)
    fig.update_layout(height=480, margin=dict(l=0, r=0, t=8, b=0), legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("上:還原價(藍)+MA25(金);下:成交量+5均量(紅)/60均量(綠)。5均量站上60均量=量能配合。")


def show():
    st.title("🎯 2560戰法")
    st.caption("世界交易冠軍**安德烈·布殊**:25日均價線(MA25)向上 + K線**踩25線起動** + 量能(**5均量 vs 60均量**)配合。")
    with st.expander("📖 四情境"):
        st.markdown("""
| 情境 | 量能 | 意義 |
|---|---|---|
| ❌ 誘惑 | 起動時 5均量 **<** 60均量 | 無量硬拉,**放棄** |
| 🟡 衝量 | 踩線起動 + 5均量**剛上穿**60均量 | 短線機會,形態未穩 |
| ✅ 做量 | 踩線起動 + 5均量**已站上**60均量一段 | 波段機會,形態已成 |
| 🎯 縮量 | 5均量早在60均量上運行 + 近1-2日**縮量(坑量)** | 牛股黑馬 |

前提:**MA25 堅決向上、股價回踩25線不破**。啟發式實作,僅供選股參考(非買賣建議)。
""")
    t1, t2 = st.tabs(["🏆 全市場選股", "📈 單股檢視"])
    with t1:
        _market()
    with t2:
        _single()
