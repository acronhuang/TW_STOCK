"""🎲 選擇權價差 —— Black-Scholes Greeks + 垂直價差策略分析（台指選擇權）。

純數學（src.analysis.options_pricing），不依賴行情資料；台指選擇權每點 50 元。
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.analysis.options_pricing import (  # noqa: E402
    RISK_FREE_RATE,
    OptionsPricer,
    VerticalSpread,
)

_STRATEGY_LABEL = {
    "bull_call": "牛市 Call 價差（看多·淨支出）",
    "bear_call": "熊市 Call 價差（看空·收權利金）",
    "bull_put": "牛市 Put 價差（看多·收權利金）",
    "bear_put": "熊市 Put 價差（看空·淨支出）",
}


def show():
    st.subheader("🎲 選擇權 Greeks / 垂直價差")
    st.caption("Black-Scholes 歐式定價；台指選擇權每點 50 元。T 以年計（天數/365）。")

    c = st.columns(5)
    S = c[0].number_input("標的價 S", value=18000.0, step=50.0)
    days = c[1].number_input("距到期天數", min_value=1, value=30, step=1)
    r = c[2].number_input("無風險利率", value=float(RISK_FREE_RATE), step=0.005, format="%.3f")
    sigma = c[3].number_input("波動率 σ", value=0.18, step=0.01, format="%.3f")
    mult = c[4].number_input("每點價值", value=50.0, step=10.0)
    T = days / 365.0

    tab1, tab2 = st.tabs(["單一選擇權 Greeks", "垂直價差策略"])

    with tab1:
        g = st.columns(2)
        K = g[0].number_input("履約價 K", value=18200.0, step=50.0, key="g_k")
        kind = g[1].selectbox("類型", ["call", "put"], key="g_kind")
        res = OptionsPricer.greeks(S, K, T, r, sigma, kind)
        mcol = st.columns(6)
        mcol[0].metric("理論價", f"{res['price']:.2f}")
        mcol[1].metric("Delta", f"{res['delta']:.4f}")
        mcol[2].metric("Gamma", f"{res['gamma']:.6f}")
        mcol[3].metric("Theta/日", f"{res['theta']:.3f}")
        mcol[4].metric("Vega/1%", f"{res['vega']:.3f}")
        mcol[5].metric("Rho/1%", f"{res['rho']:.3f}")
        st.caption(f"合約金額 ≈ 理論價 × 每點價值 = {res['price'] * mult:,.0f} 元")

    with tab2:
        s = st.columns(3)
        strategy = s[0].selectbox("策略", list(_STRATEGY_LABEL),
                                  format_func=lambda k: _STRATEGY_LABEL[k])
        k_low = s[1].number_input("低履約 K_low", value=17800.0, step=50.0, key="sp_lo")
        k_high = s[2].number_input("高履約 K_high", value=18200.0, step=50.0, key="sp_hi")
        if k_low >= k_high:
            st.error("K_low 必須小於 K_high。")
            return
        sp = VerticalSpread(strategy, k_low, k_high, S, T, r, sigma, contract_multiplier=mult)
        a = sp.analyze()

        mc = st.columns(4)
        mc[0].metric("最大獲利", f"{a['max_profit_twd']:,.0f}", f"{a['max_profit_pts']:.1f} 點")
        mc[1].metric("最大虧損", f"{a['max_loss_twd']:,.0f}", f"{a['max_loss_pts']:.1f} 點")
        mc[2].metric("損益兩平", f"{a['breakeven']}" if a["breakeven"] else "—")
        mc[3].metric("風報比", f"{a['risk_reward']}" if a["risk_reward"] else "—")

        net = a["net_cost_twd"]
        st.caption(f"{'淨支出' if net > 0 else '淨收入'} {abs(net):,.0f} 元"
                   f"　淨 Greeks：{a['net_greeks']}")
        st.markdown("**組合腿**")
        st.dataframe(pd.DataFrame(a["legs"]).rename(columns={
            "kind": "類型", "K": "履約價", "side": "方向", "premium": "權利金(點)",
        }), use_container_width=True, hide_index=True)
