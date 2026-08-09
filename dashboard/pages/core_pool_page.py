"""🏆 核心池(數據+AI+外資) —— 一鍵看選股漏斗最終名單。

全市場 → 品質快篩 → ∩ 委員買進 → 排絕對獲利+外資買超。並疊每檔技術訊號(2560/量價型態/跌深反彈)當進場時機參考。
"""
import sys
from datetime import timedelta

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.analysis.core_pool import build_core_pool  # noqa: E402
from src.analysis.strategy_2560 import classify_2560  # noqa: E402
from src.analysis.volprice_pattern import classify_tf  # noqa: E402
from src.analysis.tech_lines import rebound_potential  # noqa: E402


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=1800, show_spinner="跑選股漏斗…")
def _core():
    return build_core_pool(_db())


@st.cache_data(ttl=1800, show_spinner="讀技術訊號…")
def _tech(codes):
    db = _db()
    out = {}
    for s in codes:
        lat = db.stock_price.find_one({"stock_id": s, "date": {"$type": "date"}}, sort=[("date", -1)])
        if not lat:
            continue
        rows = []
        for r in db.stock_price.find({"stock_id": s, "date": {"$gte": lat["date"] - timedelta(days=160), "$type": "date"}},
                                     {"close": 1, "adj_close": 1, "volume": 1}).sort("date", 1):
            c = _g(r.get("adj_close")) or _g(r.get("close"))
            v = _g(r.get("volume"))
            if c and v is not None:
                rows.append((c, v))
        if len(rows) < 65:
            continue
        cl = [x[0] for x in rows]; vo = [x[1] for x in rows]
        s2560 = classify_2560(cl, vo)
        vp = classify_tf(cl, vo, "月")
        rp = rebound_potential(db, s)
        out[s] = {
            "2560": (s2560["label"].split("·")[0] if s2560 and s2560["setup"] else "—"),
            "月量價": (f"{vp['emoji']}{vp['label'].split('·')[0]}" if vp else "—"),
            "反彈潛力": (rp["verdict"] if rp else "—"),
        }
    return out


def show():
    st.title("🏆 核心池(數據 + AI + 外資)")
    st.caption("完整選股漏斗:**全市場 → 品質快篩 → ∩ 委員全票買進 → 排絕對獲利+外資買超**。"
               "疊技術訊號當進場時機參考。非買賣建議。")
    meta, core = _core()
    if meta.get("error") or core.empty:
        st.warning(f"核心池為空({meta.get('error', '')})——可能財報季或委員買進資料不足。"); return

    # 漏斗
    k = st.columns(5)
    k[0].metric("全市場", f"{meta['n_all']:,}")
    k[1].metric("品質快篩", meta["n_quality"], help="自由現金流>0·應收<60天·毛利>20%·獲利YoY>0")
    k[2].metric("委員買進", meta["n_buy"], help=f"最新週跑合議 {meta['buy_date']}")
    k[3].metric("🎯 核心池", meta["n_core"], help="品質 ∩ 買進")
    k[4].metric("財報季 / 合議日", f"{meta['quarter']}")

    tech = _tech(tuple(core["代號"].tolist()))
    t1, t2 = st.tabs([f"📋 核心名單({meta['n_core']}檔)", "📍 今日進出場訊號"])

    with t1:
        df = core.copy()
        df["2560戰法"] = df["代號"].map(lambda s: tech.get(s, {}).get("2560", "—"))
        df["月量價型態"] = df["代號"].map(lambda s: tech.get(s, {}).get("月量價", "—"))
        df["跌深反彈"] = df["代號"].map(lambda s: tech.get(s, {}).get("反彈潛力", "—"))
        cols = ["代號", "名稱", "綜合分", "EPS", "獲利(億)", "自由現金流(億)", "毛利率%", "應收週轉(天)",
                "外資10日淨買(張)", "獲利YoY%", "2560戰法", "月量價型態", "跌深反彈"]
        cols = [c for c in cols if c in df.columns]

        def _c(v):
            return f"color:{'#C62F35' if (pd.notna(v) and v > 0) else '#1F8A54' if (pd.notna(v) and v < 0) else ''}"
        st.dataframe(
            df[cols].style.map(_c, subset=["外資10日淨買(張)"])
            .map(lambda v: "color:#1F8A54;font-weight:600" if isinstance(v, str) and ("做量" in v or "跟上" in v or "反彈潛力高" in v) else "",
                 subset=[c for c in ["2560戰法", "月量價型態", "跌深反彈"] if c in df.columns])
            .format({"綜合分": "{:.2f}", "EPS": "{:.2f}", "獲利(億)": "{:,.1f}", "自由現金流(億)": "{:,.1f}",
                     "毛利率%": "{:.1f}", "應收週轉(天)": "{:.1f}", "外資10日淨買(張)": "{:+,.0f}", "獲利YoY%": "{:+.1f}"}, na_rep="—"),
            hide_index=True, width='stretch', height=560)
        st.download_button("⬇️ 下載核心池 CSV", df[cols].to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"core_pool_{meta['buy_date']}.csv", mime="text/csv")
        st.caption("綜合分=EPS+獲利+自由現金流 百分位 + 外資近10日淨買百分位×2。獲利YoY 供參(小基期偏大)。"
                   f"委員買進來自最新週跑({meta['buy_date']}),每週五更新;財報季 {meta['quarter']}。")

    with t2:
        st.caption("核心股**當日**技術訊號:🟢進場時機 / 🔴警示。同 `core_watchlist_daily` cron(每日21:30寫網頁🔔排程警報)。非買賣建議。")
        entries, warns = [], []
        for _, r in core.iterrows():
            t = tech.get(r["代號"], {})
            e, w = [], []
            if t.get("2560") in ("做量", "縮量"):
                e.append(f"2560{t['2560']}")
            vp = t.get("月量價", "")
            if "低位放量" in vp or "量增價升" in vp:
                e.append(vp)
            if t.get("反彈潛力") == "反彈潛力高":
                e.append("反彈潛力高")
            if "高位放量" in vp or "量增價跌" in vp or "量平價跌" in vp:
                w.append("月線" + vp)
            base = {"代號": r["代號"], "名稱": r["名稱"], "綜合分": r.get("綜合分"),
                    "外資10日淨買(張)": r.get("外資10日淨買(張)")}
            if e:
                entries.append({**base, "進場訊號": " / ".join(e)})
            if w:
                warns.append({**base, "警示": " / ".join(w)})
        c1, c2 = st.columns(2)
        c1.metric("🟢 進場時機", len(entries))
        c2.metric("🔴 警示", len(warns))
        if entries:
            st.markdown("##### 🟢 進場時機(基本面優質×委員買×技術對點)")
            st.dataframe(pd.DataFrame(entries).sort_values("綜合分", ascending=False)
                         .style.format({"綜合分": "{:.2f}", "外資10日淨買(張)": "{:+,.0f}"}, na_rep="—"),
                         hide_index=True, width='stretch')
        if warns:
            st.markdown("##### 🔴 警示(核心股但月線量價轉弱,留意)")
            st.dataframe(pd.DataFrame(warns).style.format({"綜合分": "{:.2f}", "外資10日淨買(張)": "{:+,.0f}"}, na_rep="—"),
                         hide_index=True, width='stretch')
        if not entries and not warns:
            st.info("今日核心股無明確進場/警示訊號(持續追蹤中)。")
