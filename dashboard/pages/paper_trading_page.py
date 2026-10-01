"""📝 模擬盤 (Paper Trading) —— 虛擬帳戶下單 / 持倉 / 損益結算。

以 src.portfolio.paper_trading.PaperTradingAccount 為後端（MongoDB 持久化）。
以最新收盤價撮合，套用台股實際交易成本（手續費+證交稅）。
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.portfolio.paper_trading import PaperTradingAccount  # noqa: E402


def show():
    st.subheader("📝 模擬盤 Paper Trading")
    st.caption("虛擬資金實戰演練：市價/限價下單、最新收盤撮合、台股手續費+證交稅、損益結算。")

    c1, c2, c3 = st.columns([2, 2, 1])
    account_id = c1.text_input("帳戶名稱", value="demo")
    init_cash = c2.number_input("初始資金", min_value=100_000, value=1_000_000, step=100_000)
    discount = c3.number_input("手續費折數", min_value=0.1, max_value=1.0, value=1.0, step=0.01)

    acc = PaperTradingAccount(account_id.strip() or "demo",
                              initial_cash=float(init_cash), fee_discount=float(discount))

    # 先撮合待成交限價單
    filled = acc.process_pending()
    if filled:
        st.success(f"撮合 {len(filled)} 筆限價單。")

    # ── 下單 ──────────────────────────────────────────────
    st.markdown("#### 下單")
    o1, o2, o3, o4, o5 = st.columns([1.2, 1, 1, 1.4, 1])
    sym = o1.text_input("代號", value="2330", max_chars=4, key="pt_sym")
    side = o2.selectbox("買賣", ["買", "賣"], key="pt_side")
    lots = o3.number_input("張數", min_value=1, value=1, step=1, key="pt_lots")
    use_limit = o4.checkbox("限價單", value=False, key="pt_uselimit")
    limit = o4.number_input("限價", min_value=0.0, value=0.0, step=0.5,
                            key="pt_limit", disabled=not use_limit)
    o5.markdown("&nbsp;", unsafe_allow_html=True)
    if o5.button("送出", type="primary", key="pt_submit"):
        lim = float(limit) if use_limit and limit > 0 else None
        fn = acc.buy if side == "買" else acc.sell
        res = fn(sym.strip(), int(lots), limit=lim)
        status = res.get("status")
        if status == "filled":
            pnl = res.get("realized_pnl")
            msg = f"✅ 成交：{side} {sym} {lots} 張 @ {res['price']}"
            if pnl is not None:
                msg += f"　已實現損益 {pnl:,.0f}"
            st.success(msg)
        elif status == "pending":
            st.info(f"⏳ 限價單已掛單（參考價 {res.get('ref_price')}），待撮合。")
        else:
            st.error(f"❌ 未成交：{res.get('reason')}")
        st.rerun()

    # ── 帳戶總覽 ──────────────────────────────────────────
    s = acc.summary()
    st.markdown("#### 帳戶總覽")
    m = st.columns(5)
    m[0].metric("總權益", f"{s['equity']:,.0f}")
    m[1].metric("現金", f"{s['cash']:,.0f}")
    m[2].metric("持倉市值", f"{s['market_value']:,.0f}")
    m[3].metric("未實現損益", f"{s['unrealized_pnl']:,.0f}")
    m[4].metric("總報酬率", f"{s['total_return_pct']:.2f}%")
    st.caption(f"已實現損益累計：{s['realized_pnl']:,.0f}　待撮合限價單：{s['pending_orders']} 筆")

    # ── 持倉 ──────────────────────────────────────────────
    st.markdown("#### 持倉")
    if s["holdings"]:
        df = pd.DataFrame(s["holdings"]).rename(columns={
            "symbol": "代號", "lots": "張數", "avg_price": "均價",
            "last_price": "現價", "market_value": "市值",
            "unrealized_pnl": "未實現損益", "return_pct": "報酬%",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("目前無持倉。")

    # ── 近期成交 ──────────────────────────────────────────
    with st.expander("近期成交紀錄"):
        trades = list(acc.db["paper_trades"].find(
            {"account_id": acc.account_id}, {"_id": 0}
        ).sort("filled_at", -1).limit(30))
        if trades:
            tdf = pd.DataFrame(trades)
            st.dataframe(tdf, use_container_width=True, hide_index=True)
        else:
            st.caption("尚無成交。")

    if st.button("⚠️ 重設此帳戶", key="pt_reset"):
        acc.reset()
        st.warning("已清空持倉/委託/成交並重設現金。")
        st.rerun()
