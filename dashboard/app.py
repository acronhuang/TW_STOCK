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
        "📊 K線圖與技術指標",
        "📈 回測結果視覺化",
        "🧮 因子分析面板",
        "📑 財報摘要儀表",
        "⚖️ 策略比較工具",
        "🔔 實時數據監控",
        "🗳️ 團隊分析",
        "🏛️ 每日選股推薦"
    ]
)

# 路由到不同頁面
if page == "🏠 系統總覽":
    from pages import home
    home.show()
elif page == "📊 K線圖與技術指標":
    from pages import charts
    charts.show()
elif page == "📈 回測結果視覺化":
    from pages import backtest_viz
    backtest_viz.show()
elif page == "🧮 因子分析面板":
    from pages import factors
    factors.show()
elif page == "📑 財報摘要儀表":
    from pages import financials
    financials.show()
elif page == "⚖️ 策略比較工具":
    from pages import strategy_compare
    strategy_compare.show()
elif page == "🔔 實時數據監控":
    from pages import monitor
    monitor.show()
elif page == "🗳️ 團隊分析":
    from pages import team
    team.show()
elif page == "🏛️ 每日選股推薦":
    from pages import picks
    picks.show()

# 頁腳
st.sidebar.markdown("---")
st.sidebar.markdown("""
    <div style='text-align: center; color: #888; font-size: 0.8rem;'>
        <p><strong>台股量化分析系統</strong></p>
        <p>版本 1.0.0</p>
        <p>© 2026 Ming</p>
    </div>
""", unsafe_allow_html=True)
