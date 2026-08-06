"""💰 融資融券(全市場榜) —— 即時讀 MongoDB,全股融資/融券餘額+增減、券資比、籌碼訊號。

資料源 margin_purchase_short_sale(上市 twse_openapi 17:50 + 上櫃 tpex_margin_sync 21:00,單位=張)。
籌碼訊號:融資增減% × 近5日股價 × 券資比 → 自動判「主力吃貨/斷頭風險/軋空候選…」(src.analysis.chip_signals)。
"""
import sys
from datetime import timedelta

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.chip_signals import margin_signal  # noqa: E402


def _i(v):
    try:
        return int(v.to_decimal()) if hasattr(v, "to_decimal") else int(v)
    except (TypeError, ValueError):
        return None


def _c(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=600, show_spinner="讀取融資融券…")
def _load():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    c = db.margin_purchase_short_sale
    d = c.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])["date"]
    codes = [r["code"] for r in c.find({"date": d}, {"code": 1}) if r.get("code")]
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": codes}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    for r in db.taiwan_stock_info.find({"stock_id": {"$in": [s for s in codes if s not in names]}},
                                       {"_id": 0, "stock_id": 1, "stock_name": 1}):
        if r.get("stock_name"):
            names[r["stock_id"]] = r["stock_name"]

    # 近5交易日股價變化(判籌碼訊號要配股價)
    sp_dates = sorted(db.stock_price.distinct("date", {"date": {"$gte": d - timedelta(days=20), "$type": "date"}}))
    d0 = sp_dates[-1]
    d5 = sp_dates[-6] if len(sp_dates) >= 6 else sp_dates[0]

    def closes(dd):
        return {r["stock_id"]: _c(r.get("close")) for r in
                db.stock_price.find({"date": dd}, {"stock_id": 1, "close": 1}) if _c(r.get("close"))}
    c0, c5 = closes(d0), closes(d5)

    rows = []
    for r in c.find({"date": d}):
        code = r.get("code")
        if not code:
            continue
        mb, pmb = _i(r.get("margin_balance")), _i(r.get("margin_prev_balance"))
        sb, psb = _i(r.get("short_balance")), _i(r.get("short_prev_balance"))
        mchg = (mb - pmb) if (mb is not None and pmb is not None) else None
        schg = (sb - psb) if (sb is not None and psb is not None) else None
        ratio = round(sb / mb * 100, 2) if (mb and sb is not None and mb > 0) else None
        pc = ((c0[code] / c5[code] - 1) * 100) if (code in c0 and code in c5 and c5[code]) else None
        label, emoji, _tone = margin_signal(mb, mchg, schg, ratio, pc)
        rows.append({
            "代號": code, "名稱": names.get(code, ""),
            "市場": "上櫃" if r.get("market") == "tpex" else "上市",
            "融資餘額": mb, "融資增減": mchg, "融券餘額": sb, "融券增減": schg,
            "券資比%": ratio, "資券相抵": _i(r.get("offset")),
            "近5日%": round(pc, 1) if pc is not None else None,
            "籌碼訊號": f"{emoji} {label}".strip(),
        })
    return str(d)[:10], pd.DataFrame(rows)


def show():
    st.title("💰 融資融券(全市場榜)")
    st.caption("即時讀 MongoDB · 上市+上櫃 · 單位:張。**籌碼訊號** = 融資增減% × 近5日股價 × 券資比 自動判讀。")
    date, df = _load()
    if df.empty:
        st.error("無資料"); return

    tm, ts = int(df["融資餘額"].sum()), int(df["融券餘額"].sum())
    k = st.columns(4)
    k[0].metric("資料日", date)
    k[1].metric("總融資餘額(萬張)", f"{tm/1e4:,.0f}")
    k[2].metric("總融券餘額(萬張)", f"{ts/1e4:,.1f}")
    k[3].metric("整體券資比", f"{ts/tm*100:.2f}%" if tm else "—")

    # 訊號速覽
    sig_counts = df["籌碼訊號"].value_counts()
    chips = [f"{s}×{n}" for s, n in sig_counts.items() if s and "中性" not in s and s != "—"]
    if chips:
        st.caption("📊 今日訊號分布:　" + "　·　".join(chips))

    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("搜尋代號/名稱", "")
    sig_opts = ["全部"] + [s for s in ["⭐ 主力吃貨", "🎯 軋空候選", "🔴 斷頭風險", "⚠️ 融資過熱", "🟢 空單回補", "🔵 認賠殺出"]
                          if s in set(df["籌碼訊號"])]
    sig = c2.selectbox("籌碼訊號", sig_opts)
    sortby = c3.selectbox("排序", ["融資增減", "融券增減", "券資比%", "近5日%", "融資餘額", "融券餘額"])

    view = df.copy()
    if sig != "全部":
        view = view[view["籌碼訊號"] == sig]
    if q.strip():
        s = q.strip().lower()
        view = view[view["代號"].str.lower().str.contains(s) | view["名稱"].str.lower().str.contains(s)]
    asc = st.checkbox("由小到大", value=False)
    view = view.sort_values(sortby, ascending=asc, na_position="last")

    st.caption(f"顯示 {len(view):,} / {len(df):,} 檔　排序:{sortby} {'↑' if asc else '↓'}")
    cols = ["代號", "名稱", "市場", "籌碼訊號", "融資餘額", "融資增減", "融券餘額", "融券增減",
            "券資比%", "近5日%", "資券相抵"]

    def _sig_color(v):
        if not isinstance(v, str):
            return ""
        if any(t in v for t in ["主力吃貨", "軋空", "空單回補"]):
            return "color:#C62F35;font-weight:600"
        if "斷頭" in v:
            return "background:rgba(198,47,53,.12);color:#C62F35;font-weight:700"
        if "過熱" in v:
            return "color:#B4841F;font-weight:600"
        return ""
    st.dataframe(
        view[cols].style
        .map(_sig_color, subset=["籌碼訊號"])
        .map(lambda v: f"color:{'#C62F35' if (pd.notna(v) and v>0) else '#1F8A54' if (pd.notna(v) and v<0) else ''}",
             subset=["融資增減", "融券增減", "近5日%"])
        .format({"融資餘額": "{:,.0f}", "融資增減": "{:+,.0f}", "融券餘額": "{:,.0f}", "融券增減": "{:+,.0f}",
                 "券資比%": "{:.2f}", "近5日%": "{:+.1f}", "資券相抵": "{:,.0f}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=560)
    st.download_button("⬇️ 下載 CSV", view[cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"margin_market_{date}.csv", mime="text/csv")

    with st.expander("📖 籌碼訊號判讀規則"):
        st.markdown("""
| 訊號 | 條件 | 意義 |
|---|---|---|
| ⭐ **主力吃貨** | 融資減 + 股價撐/漲 | 散戶下車、股價還撐 = 籌碼換手,偏多且穩 |
| 🎯 **軋空候選** | 券資比>10% + 股價不跌 | 空單多(市場均值僅~2%),遇強易軋空 |
| 🟢 **空單回補** | 融券大減 + 股價漲 | 回補買盤助漲 |
| ⚠️ **融資過熱** | 融資暴增(>5%) + 股價漲 | 散戶追價過熱,慎追 |
| 🔴 **斷頭風險** | 融資增 + 股價跌 | 散戶套牢加碼,籌碼沉重,小心斷頭殺盤 |
| 🔵 認賠殺出 | 融資減 + 股價跌 | 散戶認賠,或打底待止穩 |

門檻:股價±2%、融資增減±1%(暴增+5%)、券資比10%。近5日股價為基準。規則為啟發式,僅供籌碼參考。
""")
