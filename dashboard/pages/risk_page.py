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
# kind 的顯示名稱 ←→ 存入 DB 的值（ADR-0020）。
# 三態的意義是「這筆部位反映了誰的判斷」:我的決策 / 系統存在前的我 / 沒有人。
KIND_LABEL = {"trade": "我的決策", "opening_balance": "期初持倉", "allocation": "公司配發"}
KIND_VALUE = {v: k for k, v in KIND_LABEL.items()}


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
            "分類": lt["category"],
            # 這一筆反映誰的判斷 —— 只有「我的決策」才計入決策支援價值的統計
            "取得方式": KIND_LABEL.get(lt.get("kind") or "trade", "我的決策"),
            "來自系統建議": bool(lt.get("from_system")),
            "備註": lt["note"],
        })
    return pd.DataFrame(rows, columns=["代號", "名稱", "買進日", "股數", "價格",
                                       "分類", "取得方式", "來自系統建議", "備註"])


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
        kind = KIND_VALUE.get(str(r.get("取得方式") or "我的決策"), "trade")
        payload.append({
            "symbol": sym, "buy_date": bd,
            "shares": r.get("股數"), "price": r.get("價格"),
            "category": r.get("分類") or "波段",
            "kind": kind,
            "from_system": bool(r.get("來自系統建議")),
            "note": r.get("備註") or "",
        })
    return L.replace_lots(db, payload)


def show():
    st.title("🛡️ 持倉風控")
    db = _db()

    # ---------- ① 分批持倉明細 ----------
    st.markdown("### 📁 分批持倉明細")
    st.caption("**每一筆買進一列**(同股多次買進就多列,填**買進日**)。要新增就在表格最底下加列;"
               "刪除打勾按垃圾桶;改完按「💾 儲存」。**取得方式**:我的決策／期初持倉(系統記錄前就持有)／公司配發(無人判斷);**來自系統建議**=看了合議定案才買的。代號/買進日/股數/價格/分類都可改。"
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
            "取得方式": st.column_config.SelectboxColumn(
                "取得方式", options=list(KIND_LABEL.values()), required=True,
                help="這筆部位反映誰的判斷。只有「我的決策」計入決策支援價值的統計;"
                     "「期初持倉」是系統記錄前就持有的,「公司配發」沒有任何人的判斷"),
            "來自系統建議": st.column_config.CheckboxColumn(
                "來自系統建議", default=False,
                help="這一筆是不是看了系統的合議定案才買的。用來比較「系統推薦的」"
                     "與「自己找的」事後表現(期初持倉不適用)"),
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

    # ---------- ③ 實倉回放 + 互動式策略回測 ----------
    st.markdown("---")
    st.markdown("### 📈 實倉回放 + 互動式策略回測")
    st.caption("以**各批實際進場點**為基礎,用還原價(除權息+分割)算市值曲線。"
               "可調出場規則,即時比較「有紀律出場(策略)」vs「單純買抱」vs「同資金買 0050」。"
               "需分批有填**買進日**才納入。")
    has_date = any(lt["buy_date"] for lt in L.list_lots(db))
    if not has_date:
        st.info("目前分批都還沒填買進日 → 無法回測。請在上方明細填入各筆買進日後儲存。")
    else:
        with st.expander("⚙️ 策略參數（調整後即時重算）", expanded=True):
            k1, k2, k3, k4 = st.columns(4)
            use_sl = k1.checkbox("停損", value=True, key="rk_sl")
            sl = k1.slider("停損 %", 3, 30, 10, key="rk_slv", disabled=not use_sl) / 100
            use_tp = k2.checkbox("停利", value=False, key="rk_tp")
            tp = k2.slider("停利 %", 5, 100, 30, key="rk_tpv", disabled=not use_tp) / 100
            use_tr = k3.checkbox("移動停損", value=False, key="rk_tr")
            tr = k3.slider("移動停損 %", 3, 30, 15, key="rk_trv", disabled=not use_tr) / 100
            use_md = k4.checkbox("持有上限", value=False, key="rk_md")
            md = k4.slider("上限天數", 20, 500, 120, step=10, key="rk_mdv", disabled=not use_md)
        try:
            eq, trades = L.strategy_replay(
                db,
                stop_loss=sl if use_sl else None,
                take_profit=tp if use_tp else None,
                trailing=tr if use_tr else None,
                max_days=md if use_md else None,
            )
            if eq is None or eq.empty:
                st.warning("回測無資料(可能還原價缺失)。")
            else:
                last = eq.iloc[-1]
                c = float(last["投入成本"])
                rs = (float(last["策略市值"]) / c - 1) * 100 if c else 0
                rh = (float(last["買抱市值"]) / c - 1) * 100 if c else 0
                rb = (float(last["同資金買0050"]) / c - 1) * 100 if c else 0
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("投入成本", f"{c:,.0f}")
                m2.metric("策略市值", f"{float(last['策略市值']):,.0f}", f"{rs:+.1f}%")
                m3.metric("單純買抱", f"{float(last['買抱市值']):,.0f}", f"{rh:+.1f}%")
                m4.metric("同資金買0050", f"{float(last['同資金買0050']):,.0f}", f"{rb:+.1f}%")
                verdict = "✅ 策略優於買抱" if rs > rh + 0.1 else ("≈ 與買抱相當" if abs(rs - rh) <= 0.1 else "⚠️ 策略劣於買抱")
                st.caption(f"區間 {str(eq.index[0])[:10]} ~ {str(eq.index[-1])[:10]}　·　{verdict}（{rs - rh:+.1f} 個百分點）")
                st.line_chart(eq, height=320)
                # 交易明細
                trs = []
                for t in trades:
                    trs.append({
                        "代號": t["symbol"], "名稱": _name(t["symbol"]),
                        "買進日": str(t["buy_date"])[:10], "買價": t["buy_price"],
                        "出場日": str(t["exit_date"])[:10], "出場價": t["exit_price"],
                        "出場原因": t["reason"], "報酬%": t["ret_pct"],
                    })
                order = {"停損": 0, "移動停損": 1, "到期": 2, "停利": 3, "續持": 4}
                trs.sort(key=lambda r: (order.get(r["出場原因"], 9), r["報酬%"]))
                with st.expander(f"📋 交易明細（{len(trs)} 筆）", expanded=False):
                    st.dataframe(pd.DataFrame(trs), hide_index=True, width="stretch",
                                 column_config={"報酬%": st.column_config.NumberColumn(format="%.1f"),
                                                "買價": st.column_config.NumberColumn(format="%.2f"),
                                                "出場價": st.column_config.NumberColumn(format="%.2f")})
        except Exception as e:
            st.warning(f"回測計算失敗: {e}")

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
