#!/usr/bin/env python3
"""互動式回測：選策略/股票池/期間 → 現場跑回測引擎 → 真實績效 + 權益曲線 + 交易明細。
取代原本寫死 2024 示範數據的頁面。"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.backtesting import Backtest
from src.backtesting.strategy import (MovingAverageCrossover, RSIMeanReversion,
                                      ValueMomentum)

STRATEGIES = {
    "均線交叉 (MA Cross)": {
        "cls": MovingAverageCrossover,
        "desc": "短期均線向上/下穿越長期均線 → 買進/賣出",
        "params": {"short_window": ("短期均線", 5, 2, 60), "long_window": ("長期均線", 20, 5, 240)},
    },
    "RSI 均值回歸": {
        "cls": RSIMeanReversion,
        "desc": "RSI 低於超賣線買進、高於超買線賣出",
        "params": {"rsi_period": ("RSI 週期", 14, 2, 60), "oversold": ("超賣線", 30, 5, 50),
                   "overbought": ("超買線", 70, 50, 95)},
    },
    "價值動能": {
        "cls": ValueMomentum,
        "desc": "低本益比 + 正向動能選股",
        "params": {"pe_threshold": ("本益比上限", 15, 5, 50), "momentum_days": ("動能天數", 60, 10, 240)},
    },
}
PRESETS = {
    "電子權值 10 檔": "2330,2317,2454,2308,2382,3008,2412,2303,3711,2379",
    "金融 8 檔": "2882,2891,2886,2884,2892,2881,2885,5880",
    "傳產龍頭 8 檔": "1301,1303,1326,2002,1101,2207,9910,2105",
    "自訂輸入": "",
}
MIN_D, MAX_D = date(2021, 3, 1), date(2026, 7, 9)


@st.cache_data(show_spinner=False)
def run_backtest(strat_name, params, symbols, start, end, cash, commission):
    """跑回測，回可快取的純資料（metrics dict / equity df / trades df）。"""
    cfg = STRATEGIES[strat_name]
    strat = cfg["cls"]()
    strat.setup(**dict(params))
    bt = Backtest(strategy=strat, symbols=list(symbols), start_date=start, end_date=end,
                  initial_cash=cash, commission_rate=commission)
    res = bt.run()
    trades = pd.DataFrame([{
        "日期": str(t.date)[:10], "代號": t.symbol, "動作": t.action,
        "股數": t.shares, "價格": float(t.price), "手續費": float(getattr(t, "commission", 0)),
    } for t in res["trades"]])
    return res["metrics"].to_dict(), res["equity_curve"][["date", "equity"]].copy(), trades


def show():
    st.title("📈 互動式策略回測")
    st.caption("選策略、股票池、期間 → 現場用回測引擎跑真實歷史績效（資料 2021-03 ~ 2026-07）")

    with st.sidebar:
        st.markdown("### ⚙️ 回測設定")
        strat_name = st.selectbox("策略", list(STRATEGIES.keys()))
        cfg = STRATEGIES[strat_name]
        st.caption(cfg["desc"])
        params = []
        for key, (label, default, lo, hi) in cfg["params"].items():
            v = st.number_input(label, min_value=lo, max_value=hi, value=default)
            params.append((key, v))

        preset = st.selectbox("股票池", list(PRESETS.keys()))
        default_syms = PRESETS[preset] if preset != "自訂輸入" else "2330,2317,2454"
        syms_txt = st.text_area("股票代碼（逗號分隔，上限 30 檔）", value=default_syms, height=70)
        symbols = tuple(dict.fromkeys(s.strip() for s in syms_txt.replace("，", ",").split(",") if s.strip()))

        c1, c2 = st.columns(2)
        start = c1.date_input("開始", value=date(2023, 1, 1), min_value=MIN_D, max_value=MAX_D)
        end = c2.date_input("結束", value=date(2024, 12, 31), min_value=MIN_D, max_value=MAX_D)
        cash = st.number_input("初始資金", value=1000000, step=100000)
        commission = st.number_input("手續費率", value=0.003, min_value=0.0, max_value=0.02, format="%.4f")
        run = st.button("🚀 執行回測", type="primary", use_container_width=True)

    # 驗證
    if not symbols:
        st.info("請在左側輸入至少一檔股票代碼。"); return
    if len(symbols) > 30:
        st.error(f"股票數 {len(symbols)} 超過上限 30 檔（避免執行過久）。請減少。"); return
    if start >= end:
        st.error("開始日期需早於結束日期。"); return

    est = len(symbols) * ((end - start).days / 365) * 0.8
    if not run:
        st.info(f"目前設定：**{strat_name}**，{len(symbols)} 檔，{start} ~ {end}。\n\n"
                f"按左側「🚀 執行回測」開始。預估執行時間約 {est:.0f} 秒。")
        return

    with st.spinner(f"回測執行中…（{len(symbols)} 檔 × {(end-start).days//365 or 1} 年，約 {est:.0f} 秒）"):
        try:
            metrics, equity, trades = run_backtest(
                strat_name, tuple(params), symbols,
                start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), int(cash), float(commission))
        except Exception as e:
            st.error(f"回測失敗：{type(e).__name__}: {e}"); return

    if not metrics or metrics.get("trading_days", 0) == 0:
        st.warning("此設定沒有產生任何交易或資料，請調整參數/股票池/期間。"); return

    # 績效卡
    st.markdown("### 🎯 績效指標")
    r = metrics
    m = st.columns(4)
    m[0].metric("總報酬率", f"{r['total_return']:.2f}%")
    m[1].metric("年化報酬", f"{r['annualized_return']:.2f}%")
    m[2].metric("夏普比率", f"{r['sharpe_ratio']:.3f}")
    m[3].metric("最大回撤", f"{r['max_drawdown']:.2f}%")
    m2 = st.columns(4)
    m2[0].metric("勝率", f"{r['win_rate']:.1f}%")
    m2[1].metric("獲利因子", f"{r.get('profit_factor', 0):.2f}")
    m2[2].metric("總交易次數", r["total_trades"])
    m2[3].metric("波動率", f"{r.get('volatility', 0):.2f}%")

    # 權益曲線
    st.markdown("### 📈 權益曲線")
    eq = equity.copy()
    eq["date"] = pd.to_datetime(eq["date"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq["date"], y=eq["equity"], name="策略權益", line=dict(color="#1f77b4")))
    fig.add_hline(y=cash, line_dash="dash", line_color="gray", annotation_text="初始資金")
    fig.update_layout(height=380, margin=dict(t=20, b=20), yaxis_title="權益 (元)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # 交易明細
    st.markdown(f"### 📋 交易明細（{len(trades)} 筆）")
    if len(trades):
        st.dataframe(trades, width='stretch', hide_index=True, height=320)
        st.download_button("下載交易明細 CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"backtest_{strat_name}_{start}_{end}.csv", mime="text/csv")
    else:
        st.write("此期間無交易。")
