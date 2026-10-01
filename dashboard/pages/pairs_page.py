"""🔗 配對交易 —— 共整合 (Engle-Granger) + 價差 z-score 訊號。

後端 src.strategy.pairs_trading.PairsTrader（scipy 版 ADF）。
可分析單一股票對，或在候選池內枚舉掃描共整合對。
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.strategy.pairs_trading import PairsTrader  # noqa: E402


def show():
    st.subheader("🔗 配對交易 Pairs Trading")
    st.caption("共整合檢定找長期均衡的股票對，利用價差均值回歸交易（市場中性）。")

    pt = PairsTrader()
    tab1, tab2 = st.tabs(["單一對分析", "候選池掃描"])

    with tab1:
        c = st.columns(4)
        s1 = c[0].text_input("股票 A", value="2330", max_chars=4, key="pr_a")
        s2 = c[1].text_input("股票 B", value="2317", max_chars=4, key="pr_b")
        entry_z = c[2].number_input("進場 z", value=2.0, step=0.5, key="pr_ez")
        exit_z = c[3].number_input("出場 z", value=0.5, step=0.1, key="pr_xz")
        if st.button("分析配對", type="primary", key="pr_go"):
            res = pt.analyze_pair(s1.strip(), s2.strip(), entry_z=entry_z, exit_z=exit_z)
            if res.get("error"):
                st.error(res["error"])
            else:
                m = st.columns(5)
                m[0].metric("共整合", "✅ 是" if res["cointegrated"] else "❌ 否")
                m[1].metric("避險比 β", f"{res['hedge_ratio']}")
                m[2].metric("當前 z", f"{res['zscore']}")
                m[3].metric("半衰期(天)", f"{res['half_life_days']}" if res["half_life_days"] else "—")
                m[4].metric("相關性", f"{res['correlation']}")
                st.info(f"訊號：{res['signal']}")
                st.caption(f"ADF t={res['adf_tstat']}（p≈{res['adf_pvalue']}）　"
                           f"樣本 {res['n_days']} 日")
                bt = pt.backtest_pair(s1.strip(), s2.strip(), entry_z=entry_z, exit_z=exit_z)
                if not bt.get("error"):
                    st.caption(f"回測：{bt['trades']} 筆交易，勝率 {bt['win_rate']}%，"
                               f"價差累計 {bt['total_spread_pnl']}")

    with tab2:
        pool = st.text_input("候選池（逗號分隔 4~8 檔）", value="2330,2317,2454,2412,3045,4904")
        cc = st.columns(2)
        min_corr = cc[0].number_input("最低相關性", value=0.7, step=0.05, key="sc_corr")
        max_p = cc[1].number_input("最高 p 值", value=0.05, step=0.01, format="%.2f", key="sc_p")
        if st.button("掃描共整合對", key="sc_go"):
            syms = [x.strip() for x in pool.split(",") if x.strip()]
            if len(syms) < 2:
                st.error("至少需 2 檔。")
                return
            with st.spinner("枚舉所有股票對檢定中…"):
                pairs = pt.find_pairs(syms, min_corr=min_corr, max_pvalue=max_p)
            if not pairs:
                st.info("無符合條件的共整合對。")
            else:
                df = pd.DataFrame([{
                    "配對": " / ".join(p["pair"]),
                    "避險比": p["hedge_ratio"],
                    "相關性": p["correlation"],
                    "ADF p": p["adf_pvalue"],
                    "半衰期": p["half_life_days"],
                    "當前 z": p["zscore"],
                    "訊號": p["signal"],
                } for p in pairs])
                st.dataframe(df, use_container_width=True, hide_index=True)
