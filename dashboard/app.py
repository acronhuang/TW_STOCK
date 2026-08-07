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
        "🏠 系統總覽",
        "🏆 核心池",
        "🏛️ 每日選股推薦",
        "🗳️ 團隊分析",
        "💬 每日決策問答",
        "🔍 個股分析",
        "🛡️ 持倉風控",
        "📬 每日快訊",
        "🔔 實時數據監控",
        "🔔 排程警報",
        "📈 回測結果視覺化",
        "⚖️ 策略比較工具",
        "🎯 2560戰法",
        "💰 融資融券(全市場榜)",
        "🔎 專案知識庫檢索",
    ]
)

# 路由到不同頁面
if page == "🏠 系統總覽":
    from pages import home
    home.show()
elif page == "🏆 核心池":
    from pages import core_pool_page
    core_pool_page.show()
elif page == "🏛️ 每日選股推薦":
    from pages import picks
    picks.show()
elif page == "🗳️ 團隊分析":
    from pages import team
    team.show()
elif page == "💬 每日決策問答":
    from pages import decision_qa
    decision_qa.show()
elif page == "🔍 個股分析":
    # 階段1整併:10 頁 → 兩層子選單(面向→子項),只執行選中的 show()(避 st.tabs 執行全部→撞 widget key)
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
elif page == "🛡️ 持倉風控":
    from pages import risk_page
    risk_page.show()
elif page == "📬 每日快訊":
    from pages import notifications
    notifications.show()
elif page == "🔔 實時數據監控":
    from pages import monitor
    monitor.show()
elif page == "🔔 排程警報":
    from pages import schedule_alerts_page
    schedule_alerts_page.show()
elif page == "📈 回測結果視覺化":
    from pages import backtest_viz
    backtest_viz.show()
elif page == "⚖️ 策略比較工具":
    from pages import strategy_compare
    strategy_compare.show()
elif page == "🎯 2560戰法":
    from pages import strategy_2560_page
    strategy_2560_page.show()
elif page == "💰 融資融券(全市場榜)":
    from pages import margin_market_page
    margin_market_page.show()
elif page == "🔎 專案知識庫檢索":
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
