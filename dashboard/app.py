#!/usr/bin/env python3
"""
台股量化分析儀表板
Streamlit Dashboard for Taiwan Stock Analysis
"""

import sys
from pathlib import Path
import streamlit as st

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設定頁面配置
st.set_page_config(
    page_title="台股量化分析系統",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定義 CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    </style>
""", unsafe_allow_html=True)

# 主標題
st.markdown('<div class="main-header">📈 台股量化分析系統</div>', unsafe_allow_html=True)
st.markdown("---")

# 側邊欄導航
st.sidebar.title("🎯 導航選單")
page = st.sidebar.radio(
    "選擇功能頁面",
    [
        "🏠 總覽",
        "🎯 每日決策",
        "🔍 個股分析",
        "💼 持倉風控",
        "📊 策略研究",
        "📚 知識庫",
    ]
)

# 路由到 6 大頁(每頁內以 radio 子選單分面向,只執行選中頁 show())
if page == "🏠 總覽":
    v = st.radio("總覽", ["系統總覽", "資料監控", "排程警報"],
                 horizontal=True, key="ov_view", label_visibility="collapsed")
    if v == "系統總覽":
        from pages import home; home.show()
    elif v == "資料監控":
        from pages import monitor; monitor.show()
    else:
        from pages import schedule_alerts_page; schedule_alerts_page.show()
elif page == "🎯 每日決策":
    d = st.radio("決策", ["🏆 核心池", "🏛️ 每日選股", "🗳️ 團隊合議", "💬 決策問答", "📬 收盤快訊"],
                 horizontal=True, key="dd_view", label_visibility="collapsed")
    if d == "🏆 核心池":
        from pages import core_pool_page; core_pool_page.show()
    elif d == "🏛️ 每日選股":
        from pages import picks; picks.show()
    elif d == "🗳️ 團隊合議":
        from pages import team; team.show()
    elif d == "💬 決策問答":
        from pages import decision_qa; decision_qa.show()
    else:
        from pages import notifications; notifications.show()
elif page == "🔍 個股分析":
    grp = st.radio("面向", ["📈 技術面", "🧲 籌碼面", "📑 財報因子"], horizontal=True, key="ga_grp")
    if grp == "📈 技術面":
        sub = st.radio("子項", ["K線指標", "費波納契/支撐壓力", "量價型態"],
                       horizontal=True, key="ga_tech", label_visibility="collapsed")
        if sub == "K線指標":
            from pages import charts; charts.show()
        elif sub == "費波納契/支撐壓力":
            from pages import tech_lines_page; tech_lines_page.show()
        else:
            from pages import volprice_pattern_page; volprice_pattern_page.show()
    elif grp == "🧲 籌碼面":
        sub = st.radio("子項", ["大戶籌碼×量價", "股權分散", "融資融券(單股)"],
                       horizontal=True, key="ga_chip", label_visibility="collapsed")
        if sub == "大戶籌碼×量價":
            from pages import holder_volprice; holder_volprice.show()
        elif sub == "股權分散":
            from pages import holder_trend; holder_trend.show()
        else:
            from pages import margin_page; margin_page.show()
    else:
        sub = st.radio("子項", ["財報摘要", "財報深度", "月營收", "因子分析"],
                       horizontal=True, key="ga_fin", label_visibility="collapsed")
        if sub == "財報摘要":
            from pages import financials; financials.show()
        elif sub == "財報深度":
            from pages import financials_deep_page; financials_deep_page.show()
        elif sub == "月營收":
            from pages import revenue_page; revenue_page.show()
        else:
            from pages import factors; factors.show()
elif page == "💼 持倉風控":
    from pages import risk_page
    risk_page.show()
elif page == "📊 策略研究":
    v = st.radio("研究", ["回測視覺化", "策略比較", "2560戰法", "🎯 判斷準確度", "融資融券(全市場榜)"],
                 horizontal=True, key="sr_view", label_visibility="collapsed")
    if v == "回測視覺化":
        from pages import backtest_viz; backtest_viz.show()
    elif v == "策略比較":
        from pages import strategy_compare; strategy_compare.show()
    elif v == "2560戰法":
        from pages import strategy_2560_page; strategy_2560_page.show()
    elif v == "🎯 判斷準確度":
        from pages import verdict_accuracy_page; verdict_accuracy_page.show()
    else:
        from pages import margin_market_page; margin_market_page.show()
elif page == "📚 知識庫":
    from pages import rag_page
    rag_page.show()

# 頁腳
st.sidebar.markdown("---")
st.sidebar.markdown("""
    <div style='text-align: center; color: #888; font-size: 0.8rem;'>
        <p><strong>台股量化分析系統</strong></p>
        <p>版本 1.0.0</p>
        <p>© 2026 Ming</p>
    </div>
""", unsafe_allow_html=True)
