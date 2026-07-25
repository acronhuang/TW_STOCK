#!/usr/bin/env python3
"""🛡️ 持倉風控

① 持倉管理：一個表可改(成本/股數/分類)/刪；新增用「➕ 新增持倉」(打代號即時帶名稱)。
   單一真相 portfolio_positions,規則檢查(daily_alert_check)與風控合議都讀這份。
② 持倉風控合議 verdict(續抱/減碼/出場)：讀 risk_analysis(pipeline Step 4b)。
"""
from datetime import datetime

import pandas as pd
import streamlit as st
from bson.decimal128 import Decimal128
from pymongo import MongoClient

CATS = ["波段", "債券ETF", "長期存股", "零成本", "零股"]
NO_STOP_CATS = {"債券ETF", "長期存股", "零成本", "零股"}


def _db():
    return MongoClient("localhost", 27017)["tw_stock_analysis"]


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


@st.cache_data(ttl=120, show_spinner=False)
def _name(sym):
    ti = _db().taiwan_stock_info.find_one({"stock_id": sym}, {"stock_name": 1})
    return (ti or {}).get("stock_name", "")


def _price(db, sym):
    p = db.stock_price.find_one({"symbol": sym}, sort=[("date", -1)])
    return _f((p or {}).get("close"))


def load_enriched(db):
    rows = []
    for d in db.portfolio_positions.find({}, {"_id": 0}).sort("symbol", 1):
        sym = d["symbol"]
        cost = d.get("avg_cost") or 0
        px = _price(db, sym)
        pnl = ((px - cost) / cost * 100) if (px and cost) else None
        rows.append({"代號": sym, "名稱": _name(sym), "成本": cost, "股數": int(d.get("shares") or 0),
                     "現價": px, "損益%": round(pnl, 1) if pnl is not None else None,
                     "分類": d.get("category") or "波段"})
    return pd.DataFrame(rows, columns=["代號", "名稱", "成本", "股數", "現價", "損益%", "分類"])


def _upsert(db, sym, cost, shares, cat):
    db.portfolio_positions.update_one({"symbol": sym}, {"$set": {
        "symbol": sym, "avg_cost": float(cost or 0), "shares": int(shares or 0),
        "total_cost": float(cost or 0) * int(shares or 0),
        "category": cat, "no_stop_loss": cat in NO_STOP_CATS, "long_hold": cat == "長期存股",
        "portfolio": "main", "updated_at": datetime.now(),
    }}, upsert=True)


def save_edits(db, edited):
    """存既有列的 成本/股數/分類 變更 + 刪除被移除的列（代號為唯讀,不新增）。"""
    keep = set()
    for _, r in edited.iterrows():
        sym = str(r.get("代號") or "").strip()
        if not sym:
            continue
        keep.add(sym)
        _upsert(db, sym, r.get("成本"), r.get("股數"), r.get("分類") or "波段")
    removed = set(db.portfolio_positions.distinct("symbol")) - keep
    for sym in removed:
        db.portfolio_positions.delete_one({"symbol": sym})
    return len(keep), len(removed)


def show():
    st.title("🛡️ 持倉風控")
    db = _db()

    st.markdown("### 📁 持倉管理")
    st.caption("直接改表格的 **成本 / 股數 / 分類**；要**刪除**選列左側打勾按垃圾桶,改完按「💾 儲存變更」。"
               "**新增持倉**請用下方「➕ 新增持倉」(打代號即時顯示名稱)。分類非「波段」者不套 5% 硬止損。")
    df = load_enriched(db)
    edited = st.data_editor(
        df, num_rows="dynamic", width="stretch", key="pos_editor",
        column_config={
            "代號": st.column_config.TextColumn("代號", disabled=True),
            "名稱": st.column_config.TextColumn("名稱", disabled=True),
            "現價": st.column_config.NumberColumn("現價", disabled=True, format="%.2f"),
            "損益%": st.column_config.NumberColumn("損益%", disabled=True, format="%.1f"),
            "成本": st.column_config.NumberColumn("成本", min_value=0.0, format="%.2f"),
            "股數": st.column_config.NumberColumn("股數", min_value=0, step=1000),
            "分類": st.column_config.SelectboxColumn("分類", options=CATS, required=True),
        })
    if st.button("💾 儲存變更", type="primary"):
        try:
            u, rm = save_edits(db, edited)
            st.cache_data.clear()
            st.success(f"已更新 {u} 檔（刪除 {rm} 檔）。規則檢查與風控合議下次執行即讀新清單。")
            st.rerun()
        except Exception as e:
            st.error(f"儲存失敗: {e}")

    with st.expander("➕ 新增持倉", expanded=False):
        code = st.text_input("代號（4 碼股號）", key="add_code", placeholder="如 2330")
        code = code.strip()
        if code:
            nm = _name(code)
            if nm:
                px = _price(db, code)
                st.success(f"✅ {code} {nm}" + (f"　現價 {px}" if px else ""))
            else:
                st.warning("⚠️ 查無此代號")
        c1, c2, c3 = st.columns(3)
        cost = c1.number_input("成本", min_value=0.0, value=0.0, step=0.05, key="add_cost")
        shares = c2.number_input("股數", min_value=0, value=0, step=1000, key="add_shares")
        cat = c3.selectbox("分類", CATS, key="add_cat")
        if st.button("新增此持倉"):
            if code and _name(code):
                _upsert(db, code, cost, shares, cat)
                st.cache_data.clear()
                st.success(f"已新增 {code} {_name(code)}。")
                st.rerun()
            else:
                st.error("代號無效,無法新增。")

    st.markdown("---")
    st.markdown("### 🗳️ 持倉風控合議")
    st.caption("每晚對持倉跑 MoE 合議：續抱 / 減碼 / 出場 + 理由 + 觸發法則（pipeline Step 4b）。")
    if "risk_analysis" not in db.list_collection_names():
        st.info("尚未有風控合議結果（等 pipeline Step 4b 首次執行）。")
        return
    last = db.risk_analysis.find_one(sort=[("date", -1)], projection={"date": 1})
    if not last:
        st.info("尚未有風控合議結果。")
        return
    docs = list(db.risk_analysis.find({"date": last["date"]}))
    VMAP = {"續抱": "🟢續抱", "減碼": "🟡減碼", "出場": "🔴出場"}
    order = {"出場": 0, "減碼": 1, "續抱": 2}
    docs.sort(key=lambda d: order.get(d.get("verdict"), 9))
    rows = []
    for d in docs:
        t = d.get("tally") or {}
        rows.append({
            "代號": d.get("symbol"), "名稱": d.get("name"),
            "風控": VMAP.get(d.get("verdict"), d.get("verdict") or "—"),
            "合議": f"抱{t.get('續抱', 0)}/減{t.get('減碼', 0)}/出{t.get('出場', 0)}",
            "損益%": d.get("pnl_pct"), "觸發法則": str(d.get("rules") or ""),
            "理由": str(d.get("reason") or "")[:80],
        })
    st.caption(f"{str(last['date'])[:10]} 合議 · {len(docs)} 檔")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"損益%": st.column_config.NumberColumn(format="%.1f")})
