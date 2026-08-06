"""💰 融資融券(單股) —— 選一檔看融資/融券餘額、增減、資券比、趨勢 + 明細。

資料源 margin_purchase_short_sale(上市 twse_openapi 17:50 + 上櫃 tpex_margin_sync 21:00,單位=張)。
"""
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pymongo import MongoClient


def _i(v):
    try:
        return int(v.to_decimal()) if hasattr(v, "to_decimal") else int(v)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_list():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    ids = sorted(s for s in db.margin_purchase_short_sale.distinct("code")
                 if isinstance(s, str) and len(s) == 4 and s.isdigit())
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
    st.title("💰 融資融券(單股)")
    st.caption("融資=看多借錢買、融券=看空借券賣。**融資增、融券減=偏多;融資減、融券增=偏空**。單位:張。上市+上櫃。")
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    ids, names = _stock_list()
    if not ids:
        st.error("無融資融券資料"); return
    c1, c2 = st.columns([3, 1])
    default = ids.index("2330") if "2330" in ids else 0
    sid = c1.selectbox("股票", ids, format_func=lambda s: f"{s} {names.get(s, '')}", index=default)
    days = c2.select_slider("回看交易日", [20, 60, 120, 250], value=60)

    col = db.margin_purchase_short_sale
    lat = col.find_one({"code": sid, "date": {"$type": "date"}}, sort=[("date", -1)])
    if not lat:
        st.warning("該股無融資融券資料"); return
    rows = list(col.find({"code": sid, "date": {"$type": "date"}},
                         sort=[("date", -1)]).limit(days))
    rows.reverse()
    recs = []
    for r in rows:
        mb, sb = _i(r.get("margin_balance")), _i(r.get("short_balance"))
        recs.append({
            "date": r["date"], "融資餘額": mb, "融券餘額": sb,
            "融資買": _i(r.get("margin_buy")), "融資賣": _i(r.get("margin_sell")),
            "融券賣": _i(r.get("short_sell")), "融券買": _i(r.get("short_buy")),
            "資券相抵": _i(r.get("offset")),
            "券資比%": round(sb / mb * 100, 2) if (mb and sb is not None and mb > 0) else None,
            "market": r.get("market", "上市"),
        })
    df = pd.DataFrame(recs)
    df["融資增減"] = df["融資餘額"].diff()
    df["融券增減"] = df["融券餘額"].diff()

    # 現價序列(疊圖用)
    px = {p["date"]: (float(p["close"].to_decimal()) if hasattr(p.get("close"), "to_decimal")
                      else (float(p["close"]) if p.get("close") is not None else None))
          for p in db.stock_price.find({"stock_id": sid, "date": {"$gte": df["date"].iloc[0]}},
                                       {"date": 1, "close": 1})}
    df["收盤"] = df["date"].map(px)

    cur = df.iloc[-1]
    k = st.columns(5)
    k[0].metric("融資餘額(張)", f"{cur['融資餘額']:,}" if cur["融資餘額"] is not None else "—",
                f"{cur['融資增減']:+,.0f}" if pd.notna(cur["融資增減"]) else None)
    k[1].metric("融券餘額(張)", f"{cur['融券餘額']:,}" if cur["融券餘額"] is not None else "—",
                f"{cur['融券增減']:+,.0f}" if pd.notna(cur["融券增減"]) else None,
                delta_color="inverse")
    k[2].metric("券資比%", f"{cur['券資比%']:.1f}%" if cur["券資比%"] is not None else "—")
    k[3].metric("資券相抵(張)", f"{cur['資券相抵']:,}" if cur["資券相抵"] is not None else "—")
    k[4].metric("市場 / 資料日", f"{cur['market']} / {cur['date']:%m-%d}")

    # 籌碼訊號(融資增減% × 近5日股價 × 券資比)
    try:
        import sys
        sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
        from src.analysis.chip_signals import margin_signal
        pc5 = ((df["收盤"].iloc[-1] / df["收盤"].iloc[-6] - 1) * 100
               if len(df) >= 6 and pd.notna(df["收盤"].iloc[-6]) and df["收盤"].iloc[-6] else None)
        lbl, emj, tone = margin_signal(cur["融資餘額"], cur["融資增減"], cur["融券增減"], cur["券資比%"], pc5)
        if lbl and lbl != "—":
            det = (f"　近5日股價 {pc5:+.1f}% · 融資增減 {cur['融資增減']:+,.0f} 張 · 券資比 {cur['券資比%']}%"
                   if pc5 is not None else "")
            box = {"bear": st.error, "bull": st.success, "warn": st.warning}.get(tone, st.info)
            box(f"籌碼訊號:{emj} **{lbl}**{det}")
    except Exception:
        pass

    # 趨勢圖:融資餘額(柱)+ 融券餘額(線)+ 收盤(右軸)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["date"], y=df["融資餘額"], name="融資餘額", marker_color="#E45756", opacity=0.55),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["date"], y=df["融券餘額"], name="融券餘額", line=dict(color="#2E7D32", width=2)),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["date"], y=df["收盤"], name="收盤價", line=dict(color="#4C78A8", width=1.5, dash="dot")),
                  secondary_y=True)
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation="h", y=1.08))
    fig.update_yaxes(title_text="餘額(張)", secondary_y=False)
    fig.update_yaxes(title_text="收盤價", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**明細(近→遠)**")
    show_cols = ["date", "融資餘額", "融資增減", "融券餘額", "融券增減", "券資比%", "資券相抵", "收盤"]
    tbl = df[show_cols].sort_values("date", ascending=False).rename(columns={"date": "資料日"})
    st.dataframe(tbl.style.format({
        "融資餘額": "{:,.0f}", "融資增減": "{:+,.0f}", "融券餘額": "{:,.0f}", "融券增減": "{:+,.0f}",
        "券資比%": "{:.2f}", "資券相抵": "{:,.0f}", "收盤": "{:.2f}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=380)
    st.download_button("⬇️ 下載 CSV", tbl.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"margin_{sid}.csv", mime="text/csv")
