"""📊 量價型態(七句口訣) —— 多時框(週/月/季/半年/年)自動標籤。

七句量價口訣 + 位置過濾(低/中/高位)。與 src/analysis/volprice_pattern 共用同一分類器。
價用還原價(adj_close,避免除權息假跌),量用成交量。
"""
import sys
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.volprice_pattern import TIMEFRAMES, classify_tf, classify  # noqa: E402

TONE_BOX = {"bull": st.success, "bear": st.error, "warn": st.warning}


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _f(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = _db()
    lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
    ids = sorted(s for s in db.stock_price.distinct(
        "stock_id", {"date": {"$gte": lat["date"] - timedelta(days=20)}})
        if len(s) == 4 and s.isdigit())
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    return ids, names


@st.cache_data(ttl=1800, show_spinner=False)
def _series_one(sid, days=760):
    db = _db()
    lat = db.stock_price.find_one({"stock_id": sid, "date": {"$type": "date"}}, sort=[("date", -1)])
    if not lat:
        return []
    start = lat["date"] - timedelta(days=days)
    out = []
    for r in db.stock_price.find(
            {"stock_id": sid, "date": {"$gte": start, "$type": "date"}},
            {"date": 1, "close": 1, "adj_close": 1, "volume": 1}).sort("date", 1):
        raw = _f(r.get("close"))
        adj = _f(r.get("adj_close")) or raw
        v = _f(r.get("volume"))
        if adj and v is not None:
            out.append((r["date"], adj, v, raw))
    return out


@st.cache_data(ttl=1800, show_spinner="讀取全市場…")
def _series_all(period):
    """全市場最近 2*period 交易日的 (adj_close, volume)。回 {sid:[(c,v)...]}, names, 日期。"""
    db = _db()
    lat = db.stock_price.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])["date"]
    cal = int(period * 2 * 1.55) + 20
    start = lat - timedelta(days=cal)
    from collections import defaultdict
    ser, names = defaultdict(list), {}
    for r in db.stock_price.find(
            {"date": {"$gte": start, "$type": "date"}},
            {"stock_id": 1, "close": 1, "adj_close": 1, "volume": 1, "name": 1}).sort([("stock_id", 1), ("date", 1)]):
        sid = r["stock_id"]
        if not (len(sid) == 4 and sid.isdigit()):
            continue
        c = _f(r.get("adj_close")) or _f(r.get("close"))
        v = _f(r.get("volume"))
        if c and v is not None:
            ser[sid].append((c, v))
        if r.get("name"):
            names[sid] = r["name"]
    return dict(ser), names, str(lat)[:10]


def _single(ids, names):
    c1, c2 = st.columns([3, 1])
    default = ids.index("2330") if "2330" in ids else 0
    sid = c1.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    rows = _series_one(sid)
    if len(rows) < 20:
        st.warning("資料不足"); return
    closes = [r[1] for r in rows]
    vols = [r[2] for r in rows]

    st.markdown(f"#### {sid} {names.get(sid, '')} — 五時框量價型態")
    cards = st.columns(len(TIMEFRAMES))
    recs = []
    for i, tf in enumerate(TIMEFRAMES):
        r = classify_tf(closes, vols, tf)
        if not r:
            cards[i].metric(tf, "資料不足"); continue
        cards[i].metric(tf, f"{r['emoji']} {r['label'].split('·')[0]}",
                        f"{r['報酬%']:+.1f}% 量{r['量變%']:+.0f}%")
        recs.append({"時框": tf, "型態標籤": f"{r['emoji']} {r['label']}",
                     "位置": {"低": "低位", "中": "中位", "高": "高位"}[r["位置"]],
                     "量": r["量"], "價": r["價"], "期間報酬%": r["報酬%"],
                     "量變%": r["量變%"], "位階%": r["位階%"]})
    if recs:
        st.dataframe(pd.DataFrame(recs).style.format(
            {"期間報酬%": "{:+.1f}", "量變%": "{:+.1f}", "位階%": "{:.0f}"}, na_rep="—"),
            hide_index=True, use_container_width=True)

    # 還原價 + 量圖(近250日)
    df = pd.DataFrame(rows[-250:], columns=["date", "adj", "vol", "raw"])
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.03)
    fig.add_trace(go.Scatter(x=df["date"], y=df["adj"], name="還原價", line=dict(color="#4C78A8", width=1.6)), row=1, col=1)
    up = df["adj"].diff() >= 0
    fig.add_trace(go.Bar(x=df["date"], y=df["vol"], name="量",
                         marker_color=["#E45756" if u else "#2E7D32" for u in up]), row=2, col=1)
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=8, b=0), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("價=還原價(除權息已還原,避免假跌);量色:紅=較前日增、綠=減。標籤用還原價計算。")


def _market(names_hint):
    tf = st.radio("時框", list(TIMEFRAMES), horizontal=True, index=1)
    period, pth, vth = TIMEFRAMES[tf]
    ser, names, date = _series_all(period)
    names = {**names, **names_hint}
    rows = []
    for sid, sv in ser.items():
        if len(sv) < period * 2:
            continue
        r = classify(the := [x[0] for x in sv], [x[1] for x in sv], period, pth, vth)
        if not r:
            continue
        rows.append({"代號": sid, "名稱": names.get(sid, ""),
                     "型態標籤": f"{r['emoji']} {r['label']}",
                     "位置": {"低": "低位", "中": "中位", "高": "高位"}[r["位置"]],
                     "量": r["量"], "價": r["價"], "期間報酬%": r["報酬%"],
                     "量變%": r["量變%"], "位階%": r["位階%"], "收盤": round(the[-1], 2)})
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("無資料"); return
    st.caption(f"資料日 {date} · {tf}時框(比較最近 {period} vs 前 {period} 交易日,價漲跌門檻±{pth}%,量增縮門檻±{vth}%)")

    counts = df["型態標籤"].value_counts()
    chips = "　·　".join(f"{k}×{v}" for k, v in counts.items())
    st.caption("📊 型態分布:　" + chips)

    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("搜尋代號/名稱", "")
    labs = ["全部"] + list(counts.index)
    pick = c2.selectbox("型態標籤", labs)
    sortby = c3.selectbox("排序", ["期間報酬%", "量變%", "位階%"])
    view = df.copy()
    if pick != "全部":
        view = view[view["型態標籤"] == pick]
    if q.strip():
        s = q.strip().lower()
        view = view[view["代號"].str.lower().str.contains(s) | view["名稱"].str.lower().str.contains(s)]
    asc = st.checkbox("由小到大", value=False)
    view = view.sort_values(sortby, ascending=asc, na_position="last")
    st.caption(f"顯示 {len(view):,} / {len(df):,} 檔")

    def _tone(v):
        if not isinstance(v, str):
            return ""
        if any(t in v for t in ["跑路", "出局", "減倉"]):
            return "color:#C62F35;font-weight:600"
        if any(t in v for t in ["跟上", "買入", "加倉"]):
            return "color:#1F8A54;font-weight:600"
        if any(t in v for t in ["拿好", "持有"]):
            return "color:#B4841F"
        return ""
    cols = ["代號", "名稱", "型態標籤", "位置", "量", "價", "期間報酬%", "量變%", "位階%", "收盤"]
    st.dataframe(
        view[cols].style.map(_tone, subset=["型態標籤"])
            .map(lambda v: f"color:{'#C62F35' if (pd.notna(v) and v>0) else '#1F8A54' if (pd.notna(v) and v<0) else ''}",
                 subset=["期間報酬%", "量變%"])
            .format({"期間報酬%": "{:+.1f}", "量變%": "{:+.1f}", "位階%": "{:.0f}", "收盤": "{:.2f}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=540)
    st.download_button("⬇️ 下載 CSV", view[cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"volprice_{tf}_{date}.csv", mime="text/csv")


def show():
    st.title("📊 量價型態(七句口訣)")
    st.caption("七句量價口訣 **+ 位置過濾**(低/中/高位),多時框自動標籤。價用還原價、量用成交量。")
    with st.expander("📖 七句口訣 × 位置"):
        st.markdown("""
| 型態 | 口訣 | 訊號 |
|---|---|---|
| 低位放量 | 跟上 🟢 | 底部資金進場 |
| 高位放量 | 跑路 🔴 | 高檔出貨 |
| 低位無量 | 等待 ⚪ | 賣壓竭盡待確認 |
| 高位無量 | 拿好·防背離 🟠 | 惜售續抱但留意背離 |
| 量增價升 | 果斷買入 🟢 | 放量上漲 |
| 量縮價升 | 安心持有 🔵 | 惜售續漲(設防) |
| 量增價跌 | 及時減倉 🟠 | 放量下跌 |
| 量平價跌 | 堅決出局 🔴 | 無量陰跌 |
| 量平價升 | 擇機加倉 🟢 | 溫和推升 |

位置=現價在近期區間的相對高低(補口訣「只看單根量價」的盲點)。時框越長,漲跌/量能門檻越大。
""")
    ids, names = _stock_list()
    t1, t2 = st.tabs(["📈 單股(五時框)", "🏆 全市場(單時框掃描)"])
    with t1:
        _single(ids, names)
    with t2:
        _market(names)
