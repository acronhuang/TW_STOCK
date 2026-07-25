#!/usr/bin/env python3
"""🛡️ 持倉風控

① 分批持倉明細：一個表記錄每一筆買進(代號/買進日/股數/價格/分類/備註),
   同股多次買進就多列。單一真相 portfolio_lots → 自動彙總回 portfolio_positions
   (Phase2 風控 daily_alert_check / risk_deliberation 不受影響,仍讀彙總部位)。
② 彙總部位(唯讀,由分批自動加總:總股數/平均成本/損益)。
③ 實倉回放：從各批實際進場日,用還原價畫組合報酬曲線 vs 同資金買 0050。
④ 持倉風控合議 verdict(續抱/減碼/出場):讀 risk_analysis(pipeline Step 4b)。
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from bson.decimal128 import Decimal128
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.portfolio import lots as L  # noqa: E402

CATS = L.CATS


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


def _lots_df(db):
    rows = []
    for lt in L.list_lots(db):
        bd = lt["buy_date"]
        rows.append({
            "代號": lt["symbol"], "名稱": _name(lt["symbol"]),
            "買進日": pd.to_datetime(bd) if bd else None,
            "股數": lt["shares"], "價格": lt["price"],
            "分類": lt["category"], "備註": lt["note"],
        })
    return pd.DataFrame(rows, columns=["代號", "名稱", "買進日", "股數", "價格", "分類", "備註"])


def _agg_df(db):
    rows = []
    for d in db.portfolio_positions.find({}, {"_id": 0}).sort("symbol", 1):
        sym = d["symbol"]
        cost = _f(d.get("avg_cost")) or 0
        px = _price(db, sym)
        pnl = ((px - cost) / cost * 100) if (px and cost) else None
        rows.append({"代號": sym, "名稱": _name(sym), "均價": round(cost, 2),
                     "總股數": int(_f(d.get("shares")) or 0),
                     "現價": px, "損益%": round(pnl, 1) if pnl is not None else None,
                     "分類": d.get("category") or "波段"})
    return pd.DataFrame(rows, columns=["代號", "名稱", "均價", "總股數", "現價", "損益%", "分類"])


def _save_lots(db, edited):
    payload = []
    for _, r in edited.iterrows():
        sym = str(r.get("代號") or "").strip()
        if not sym:
            continue
        bd = r.get("買進日")
        if pd.notna(bd) and bd is not None:
            bd = pd.to_datetime(bd)
            bd = datetime(bd.year, bd.month, bd.day)
        else:
            bd = None
        payload.append({
            "symbol": sym, "buy_date": bd,
            "shares": r.get("股數"), "price": r.get("價格"),
            "category": r.get("分類") or "波段", "note": r.get("備註") or "",
        })
    return L.replace_lots(db, payload)


def show():
    st.title("🛡️ 持倉風控")
    db = _db()

    # ---------- ① 分批持倉明細 ----------
    st.markdown("### 📁 分批持倉明細")
    st.caption("**每一筆買進一列**(同股多次買進就多列,填**買進日**)。要新增就在表格最底下加列;"
               "刪除打勾按垃圾桶;改完按「💾 儲存」。代號/買進日/股數/價格/分類都可改。"
               "系統會自動加總成下方「彙總部位」給每晚風控用。")
    df = _lots_df(db)
    edited = st.data_editor(
        df, num_rows="dynamic", width="stretch", key="lots_editor",
        column_config={
            "代號": st.column_config.TextColumn("代號", required=True),
            "名稱": st.column_config.TextColumn("名稱", disabled=True, help="存檔後自動帶入"),
            "買進日": st.column_config.DateColumn("買進日", format="YYYY-MM-DD",
                                                help="這一筆的實際成交日(供實倉回放)"),
            "股數": st.column_config.NumberColumn("股數", min_value=0, step=1000, required=True),
            "價格": st.column_config.NumberColumn("價格", min_value=0.0, format="%.2f", required=True),
            "分類": st.column_config.SelectboxColumn("分類", options=CATS, required=True),
            "備註": st.column_config.TextColumn("備註"),
        })
    if st.button("💾 儲存", type="primary"):
        try:
            n = _save_lots(db, edited)
            st.cache_data.clear()
            st.success(f"已存 {n} 筆分批,並自動彙總部位。規則檢查與風控合議下次執行即讀新清單。")
            st.rerun()
        except Exception as e:
            st.error(f"儲存失敗: {e}")

    # ---------- ② 彙總部位 ----------
    st.markdown("### 📊 彙總部位（自動加總,唯讀）")
    agg = _agg_df(db)
    if agg.empty:
        st.info("尚無持倉。")
    else:
        st.dataframe(agg, hide_index=True, width="stretch", column_config={
            "均價": st.column_config.NumberColumn(format="%.2f"),
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "損益%": st.column_config.NumberColumn(format="%.1f"),
        })

    # ---------- ③ 實倉回放 ----------
    st.markdown("---")
    st.markdown("### 📈 實倉回放")
    st.caption("從**各批實際買進日**起,用還原價(還原除權息+分割)算組合市值曲線,對比「同一筆錢、同一天改買 0050」。"
               "需要分批有填**買進日**才會納入。")
    has_date = any(lt["buy_date"] for lt in L.list_lots(db))
    if not has_date:
        st.info("目前分批都還沒填買進日 → 無法回放。請在上方明細填入各筆買進日後儲存。")
    else:
        try:
            rep = L.equity_replay(db)
            if rep is None or rep.empty:
                st.warning("回放無資料(可能還原價缺失)。")
            else:
                last = rep.iloc[-1]
                cost = float(last["投入成本"])
                rp = (float(last["持倉市值"]) / cost - 1) * 100 if cost else 0
                rb = (float(last["同資金買0050"]) / cost - 1) * 100 if cost else 0
                c1, c2, c3 = st.columns(3)
                c1.metric("投入成本", f"{cost:,.0f}")
                c2.metric("持倉市值", f"{float(last['持倉市值']):,.0f}", f"{rp:+.1f}%")
                c3.metric("同資金買0050", f"{float(last['同資金買0050']):,.0f}", f"{rb:+.1f}%")
                st.caption(f"區間 {str(rep.index[0])[:10]} ~ {str(rep.index[-1])[:10]}　·　"
                           f"{'✅ 跑贏大盤' if rp > rb else '⚠️ 跑輸大盤'} {abs(rp - rb):.1f} 個百分點")
                st.line_chart(rep, height=320)
        except Exception as e:
            st.warning(f"回放計算失敗: {e}")

    # ---------- ④ 持倉風控合議 ----------
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
