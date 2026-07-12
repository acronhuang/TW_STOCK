#!/usr/bin/env python3
"""
因子分析面板
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pymongo import MongoClient
from datetime import datetime, timedelta
import numpy as np

def show():
    st.title("🧮 因子分析面板")
    st.markdown("分析量化因子的時間序列、分布和相關性")
    
    # 連接資料庫
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 選擇股票（過濾 None）
    symbols = [s for s in db.stock_price.distinct('symbol') if s is not None]
    symbols = sorted(symbols)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_symbol = st.selectbox(
            "選擇股票",
            symbols,
            index=symbols.index('2330') if '2330' in symbols else 0
        )
    
    with col2:
        # 獲取股票名稱
        stock_info = db.taiwan_stock_info.find_one(
            {'stock_id': selected_symbol},
            {'stock_name': 1}
        )
        stock_name = stock_info.get('stock_name', '') if stock_info else ''
        st.metric("公司名稱", stock_name)
    
    # 日期範圍選擇
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "起始日期",
            datetime(2024, 1, 1)
        )
    with col2:
        end_date = st.date_input(
            "結束日期",
            datetime(2024, 12, 31)
        )
    
    # 獲取因子數據
    factors_cursor = db.stock_factors.find(
        {
            'symbol': selected_symbol,
            'date': {
                '$gte': datetime.combine(start_date, datetime.min.time()),
                '$lte': datetime.combine(end_date, datetime.max.time())
            }
        }
    ).sort('date', 1)
    
    factors_data = list(factors_cursor)
    
    if not factors_data:
        st.warning(f"沒有找到 {selected_symbol} 在此期間的因子數據")
        return
    
    # 轉換為 DataFrame
    df = pd.DataFrame(factors_data)
    df['date'] = pd.to_datetime(df['date'])
    
    st.success(f"找到 {len(df)} 筆數據記錄")
    
    # 因子分類
    value_factors = ['pe_ratio', 'pb_ratio', 'dividend_yield', 'earnings_yield']
    momentum_factors = ['return_1m', 'return_3m', 'return_6m', 'return_12m', 'rsi_14', 'volatility_30d']
    quality_factors = ['roe', 'roa', 'profit_margin', 'operating_margin', 'current_ratio', 'debt_ratio']
    
    # 選擇因子類別
    factor_type = st.radio(
        "選擇因子類別",
        ["價值因子", "動能因子", "質量因子", "全部"],
        horizontal=True
    )
    
    if factor_type == "價值因子":
        selected_factors = value_factors
    elif factor_type == "動能因子":
        selected_factors = momentum_factors
    elif factor_type == "質量因子":
        selected_factors = quality_factors
    else:
        selected_factors = value_factors + momentum_factors + quality_factors
    
    # 過濾存在的因子
    available_factors = [f for f in selected_factors if f in df.columns and df[f].notna().any()]
    
    if not available_factors:
        st.warning(f"此類別沒有可用的因子數據")
        return
    
    # Tab 分頁
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 時間序列", 
        "📊 分布分析", 
        "🔗 相關性矩陣",
        "📋 統計摘要"
    ])
    
    # Tab 1: 時間序列圖
    with tab1:
        st.subheader("因子時間序列")
        
        # 選擇要顯示的因子
        factors_to_plot = st.multiselect(
            "選擇要顯示的因子",
            available_factors,
            default=available_factors[:4]
        )
        
        if factors_to_plot:
            # 創建子圖
            fig = make_subplots(
                rows=len(factors_to_plot),
                cols=1,
                subplot_titles=[f.replace('_', ' ').title() for f in factors_to_plot],
                vertical_spacing=0.08
            )
            
            for i, factor in enumerate(factors_to_plot, 1):
                # 過濾有效數據
                factor_df = df[df[factor].notna()][['date', factor]]
                
                if not factor_df.empty:
                    fig.add_trace(
                        go.Scatter(
                            x=factor_df['date'],
                            y=factor_df[factor],
                            mode='lines',
                            name=factor,
                            line=dict(width=2),
                            showlegend=False
                        ),
                        row=i, col=1
                    )
                    
                    # 添加移動平均線
                    if len(factor_df) >= 20:
                        ma20 = factor_df[factor].rolling(window=20).mean()
                        fig.add_trace(
                            go.Scatter(
                                x=factor_df['date'],
                                y=ma20,
                                mode='lines',
                                name=f'{factor} MA20',
                                line=dict(width=1, dash='dash'),
                                opacity=0.6,
                                showlegend=False
                            ),
                            row=i, col=1
                        )
            
            fig.update_layout(
                height=300 * len(factors_to_plot),
                showlegend=False,
                hovermode='x unified'
            )
            
            fig.update_xaxes(title_text="日期")
            
            st.plotly_chart(fig, width="stretch")
    
    # Tab 2: 分布分析
    with tab2:
        st.subheader("因子分布分析")
        
        # 選擇因子
        factor_for_dist = st.selectbox(
            "選擇因子",
            available_factors,
            key='dist_factor'
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 直方圖
            factor_data = df[df[factor_for_dist].notna()][factor_for_dist]
            
            fig = px.histogram(
                factor_data,
                nbins=50,
                title=f"{factor_for_dist.replace('_', ' ').title()} 分布",
                labels={'value': factor_for_dist, 'count': '頻數'}
            )
            
            fig.add_vline(
                x=factor_data.mean(),
                line_dash="dash",
                line_color="red",
                annotation_text=f"平均: {factor_data.mean():.2f}"
            )
            
            fig.add_vline(
                x=factor_data.median(),
                line_dash="dash",
                line_color="green",
                annotation_text=f"中位數: {factor_data.median():.2f}"
            )
            
            st.plotly_chart(fig, width="stretch")
        
        with col2:
            # 箱型圖
            fig = go.Figure()
            fig.add_trace(go.Box(
                y=factor_data,
                name=factor_for_dist,
                boxmean='sd'
            ))
            
            fig.update_layout(
                title=f"{factor_for_dist.replace('_', ' ').title()} 箱型圖",
                yaxis_title=factor_for_dist
            )
            
            st.plotly_chart(fig, width="stretch")
        
        # 統計量
        st.markdown("### 統計量")
        stats_df = pd.DataFrame({
            '指標': ['平均值', '中位數', '標準差', '最小值', '最大值', '偏度', '峰度'],
            '數值': [
                f"{factor_data.mean():.4f}",
                f"{factor_data.median():.4f}",
                f"{factor_data.std():.4f}",
                f"{factor_data.min():.4f}",
                f"{factor_data.max():.4f}",
                f"{factor_data.skew():.4f}",
                f"{factor_data.kurtosis():.4f}"
            ]
        })
        st.dataframe(stats_df, width="stretch", hide_index=True)
    
    # Tab 3: 相關性矩陣
    with tab3:
        st.subheader("因子相關性矩陣")
        
        # 計算相關性
        corr_factors = [f for f in available_factors if df[f].notna().sum() > 10]
        
        if len(corr_factors) >= 2:
            corr_df = df[corr_factors].corr()
            
            # 熱力圖
            fig = px.imshow(
                corr_df,
                color_continuous_scale='RdBu_r',
                aspect='auto',
                title='因子相關性熱力圖',
                zmin=-1, zmax=1
            )
            
            fig.update_layout(
                height=600,
                xaxis_title='',
                yaxis_title=''
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # 顯示高相關因子對
            st.markdown("### 高相關因子對（|相關係數| > 0.7）")
            high_corr = []
            for i in range(len(corr_df)):
                for j in range(i+1, len(corr_df)):
                    corr_val = corr_df.iloc[i, j]
                    if abs(corr_val) > 0.7:
                        high_corr.append({
                            '因子 1': corr_df.index[i],
                            '因子 2': corr_df.columns[j],
                            '相關係數': f"{corr_val:.4f}"
                        })
            
            if high_corr:
                st.dataframe(pd.DataFrame(high_corr), width="stretch", hide_index=True)
            else:
                st.info("沒有高度相關的因子對")
        else:
            st.warning("需要至少 2 個有效因子來計算相關性")
    
    # Tab 4: 統計摘要
    with tab4:
        st.subheader("因子統計摘要")
        
        # 創建統計摘要表
        summary_data = []
        
        for factor in available_factors:
            factor_values = df[df[factor].notna()][factor]
            
            if len(factor_values) > 0:
                summary_data.append({
                    '因子': factor.replace('_', ' ').title(),
                    '數據點數': len(factor_values),
                    '覆蓋率': f"{len(factor_values) / len(df) * 100:.1f}%",
                    '平均值': f"{factor_values.mean():.4f}",
                    '中位數': f"{factor_values.median():.4f}",
                    '標準差': f"{factor_values.std():.4f}",
                    '最小值': f"{factor_values.min():.4f}",
                    '最大值': f"{factor_values.max():.4f}"
                })
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, width="stretch", hide_index=True)
        
        # 下載按鈕
        csv = summary_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載統計摘要 CSV",
            data=csv,
            file_name=f"factor_summary_{selected_symbol}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    # 橫斷面分析（所有股票在某一天的因子值）
    st.markdown("---")
    st.subheader("📊 橫斷面分析")
    st.markdown("查看所有股票在特定日期的因子分布")
    
    cross_date = st.date_input(
        "選擇日期",
        datetime(2024, 12, 31),
        key='cross_date'
    )
    
    cross_factor = st.selectbox(
        "選擇因子",
        available_factors,
        key='cross_factor'
    )
    
    if st.button("🔍 分析橫斷面"):
        # 獲取該日期所有股票的因子值
        cross_data = db.stock_factors.find(
            {
                'date': datetime.combine(cross_date, datetime.min.time()),
                cross_factor: {'$ne': None}
            },
            {'symbol': 1, cross_factor: 1}
        )
        
        cross_list = list(cross_data)
        
        if cross_list:
            cross_df = pd.DataFrame(cross_list)
            cross_df = cross_df.sort_values(cross_factor, ascending=False)
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Top 20 排名
                st.markdown(f"### Top 20 - {cross_factor.replace('_', ' ').title()}")
                
                fig = px.bar(
                    cross_df.head(20),
                    x='symbol',
                    y=cross_factor,
                    title=f"Top 20 股票 - {cross_date}",
                    labels={'symbol': '股票代碼', cross_factor: '因子值'}
                )
                
                st.plotly_chart(fig, width="stretch")
            
            with col2:
                st.markdown("### 統計資訊")
                st.metric("股票數", len(cross_df))
                st.metric("平均值", f"{cross_df[cross_factor].mean():.4f}")
                st.metric("中位數", f"{cross_df[cross_factor].median():.4f}")
                st.metric("標準差", f"{cross_df[cross_factor].std():.4f}")
                
                # 當前股票排名
                if selected_symbol in cross_df['symbol'].values:
                    rank = (cross_df['symbol'] == selected_symbol).idxmax() + 1
                    percentile = (rank / len(cross_df)) * 100
                    st.metric(
                        f"{selected_symbol} 排名",
                        f"{rank} / {len(cross_df)}",
                        f"前 {percentile:.1f}%"
                    )
        else:
            st.warning(f"該日期沒有可用的 {cross_factor} 數據")

if __name__ == '__main__':
    show()
