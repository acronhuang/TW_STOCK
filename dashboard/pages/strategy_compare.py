#!/usr/bin/env python3
"""
策略比較工具
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path
import json

def calculate_metrics(equity_df, trades_df=None):
    """計算績效指標"""
    if equity_df.empty:
        return {}
    
    returns = equity_df['equity'].pct_change().dropna()
    
    # 計算指標
    total_return = (equity_df['equity'].iloc[-1] / equity_df['equity'].iloc[0] - 1) * 100
    
    # 年化報酬率
    days = (equity_df['date'].iloc[-1] - equity_df['date'].iloc[0]).days
    annual_return = ((1 + total_return/100) ** (365/days) - 1) * 100 if days > 0 else 0
    
    # 夏普比率（假設無風險利率為 0）
    sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0
    
    # 最大回撤
    cummax = equity_df['equity'].cummax()
    drawdown = (equity_df['equity'] - cummax) / cummax
    max_drawdown = drawdown.min() * 100
    
    # 波動率
    volatility = returns.std() * (252 ** 0.5) * 100
    
    # 交易相關指標
    win_rate = None
    profit_factor = None
    total_trades = None
    
    if trades_df is not None and not trades_df.empty:
        total_trades = len(trades_df)
        
        # 檢查可能的損益列名
        profit_col = None
        for col_name in ['profit', 'pnl', 'return', 'profit_loss', 'return_pct']:
            if col_name in trades_df.columns:
                profit_col = col_name
                break
        
        if profit_col is not None:
            wins = trades_df[trades_df[profit_col] > 0]
            losses = trades_df[trades_df[profit_col] <= 0]
            
            win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
            
            total_profit = wins[profit_col].sum() if not wins.empty else 0
            total_loss = abs(losses[profit_col].sum()) if not losses.empty else 0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'volatility': volatility,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_trades': total_trades
    }

def show():
    st.title("⚖️ 策略比較工具")
    st.markdown("比較多個回測策略的績效表現")
    
    # 獲取可用的回測結果
    charts_dir = Path(__file__).parent.parent.parent / 'charts'
    
    # 查找所有權益曲線文件
    equity_files = list(charts_dir.glob('*_equity.csv'))
    
    if not equity_files:
        st.warning("沒有找到回測結果文件")
        st.info("請先運行回測策略以生成數據")
        return
    
    # 提取策略名稱
    available_strategies = {}
    for file in equity_files:
        strategy_name = file.stem.replace('_equity', '').replace('_', ' ').title()
        available_strategies[strategy_name] = file
    
    st.success(f"找到 {len(available_strategies)} 個策略")
    
    # 選擇要比較的策略
    selected_strategies = st.multiselect(
        "選擇要比較的策略（最多 4 個）",
        list(available_strategies.keys()),
        default=list(available_strategies.keys())[:2]
    )
    
    if not selected_strategies:
        st.info("請至少選擇一個策略")
        return
    
    if len(selected_strategies) > 4:
        st.warning("最多只能比較 4 個策略")
        selected_strategies = selected_strategies[:4]
    
    # 載入策略數據
    strategies_data = {}
    
    for strategy_name in selected_strategies:
        equity_file = available_strategies[strategy_name]
        equity_df = pd.read_csv(equity_file)
        equity_df['date'] = pd.to_datetime(equity_df['date'])
        
        # 嘗試載入交易記錄
        trades_file = equity_file.parent / equity_file.name.replace('_equity.csv', '_trades.csv')
        trades_df = None
        if trades_file.exists() and trades_file.stat().st_size > 0:
            try:
                trades_df = pd.read_csv(trades_file)
                if trades_df.empty:
                    trades_df = None
                elif 'date' in trades_df.columns:
                    trades_df['date'] = pd.to_datetime(trades_df['date'])
            except (pd.errors.EmptyDataError, pd.errors.ParserError):
                # 文件為空或格式錯誤，忽略
                trades_df = None
        
        # 計算指標
        metrics = calculate_metrics(equity_df, trades_df)
        
        strategies_data[strategy_name] = {
            'equity': equity_df,
            'trades': trades_df,
            'metrics': metrics
        }
    
    # Tab 分頁
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 績效比較",
        "📈 權益曲線",
        "📉 回撤分析",
        "📋 詳細指標"
    ])
    
    # Tab 1: 績效比較
    with tab1:
        st.subheader("關鍵績效指標對比")
        
        # 構建比較表
        metrics_comparison = []
        
        for strategy_name, data in strategies_data.items():
            metrics = data['metrics']
            metrics_comparison.append({
                '策略': strategy_name,
                '總報酬率 (%)': f"{metrics['total_return']:.2f}",
                '年化報酬 (%)': f"{metrics['annual_return']:.2f}",
                '夏普比率': f"{metrics['sharpe_ratio']:.3f}",
                '最大回撤 (%)': f"{metrics['max_drawdown']:.2f}",
                '波動率 (%)': f"{metrics['volatility']:.2f}",
                '勝率 (%)': f"{metrics['win_rate']:.2f}" if metrics['win_rate'] is not None else 'N/A',
                '獲利因子': f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] is not None else 'N/A',
                '交易次數': metrics['total_trades'] if metrics['total_trades'] is not None else 'N/A'
            })
        
        comparison_df = pd.DataFrame(metrics_comparison)
        st.dataframe(comparison_df, width="stretch", hide_index=True)
        
        # 雷達圖比較
        st.markdown("### 策略雷達圖")
        
        fig = go.Figure()
        
        categories = ['年化報酬', '夏普比率', '最大回撤', '勝率', '獲利因子']
        
        colors = ['blue', 'red', 'green', 'orange']
        
        for i, (strategy_name, data) in enumerate(strategies_data.items()):
            metrics = data['metrics']
            
            # 正規化數值（轉換為 0-100 範圍）
            values = [
                min(metrics['annual_return'] * 2, 100),  # 年化報酬 (50% = 100分)
                min(metrics['sharpe_ratio'] * 50, 100),  # 夏普比率 (2.0 = 100分)
                min(abs(metrics['max_drawdown']) * 5, 100),  # 最大回撤 (20% = 100分，越小越好)
                metrics['win_rate'] if metrics['win_rate'] else 50,  # 勝率
                min(metrics['profit_factor'] * 50, 100) if metrics['profit_factor'] else 50  # 獲利因子 (2.0 = 100分)
            ]
            
            # 回撤要反轉（越小越好）
            values[2] = 100 - values[2]
            
            fig.add_trace(go.Scatterpolar(
                r=values + [values[0]],  # 閉合圖形
                theta=categories + [categories[0]],
                fill='toself',
                name=strategy_name,
                line_color=colors[i]
            ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100]
                )
            ),
            showlegend=True,
            height=500
        )
        
        st.plotly_chart(fig, width="stretch")
        
        # 風險報酬散點圖
        st.markdown("### 風險報酬散點圖")
        
        scatter_data = []
        for strategy_name, data in strategies_data.items():
            metrics = data['metrics']
            scatter_data.append({
                'strategy': strategy_name,
                'return': metrics['annual_return'],
                'risk': metrics['volatility']
            })
        
        scatter_df = pd.DataFrame(scatter_data)
        
        fig = px.scatter(
            scatter_df,
            x='risk',
            y='return',
            text='strategy',
            size=[100] * len(scatter_df),
            color='strategy',
            labels={'risk': '波動率 (%)', 'return': '年化報酬 (%)'}
        )
        
        fig.update_traces(textposition='top center')
        
        fig.update_layout(
            title='風險報酬圖（左上角為最佳）',
            height=500,
            showlegend=False
        )
        
        # 添加參考線
        avg_return = scatter_df['return'].mean()
        avg_risk = scatter_df['risk'].mean()
        
        fig.add_hline(y=avg_return, line_dash="dash", line_color="gray", annotation_text="平均報酬")
        fig.add_vline(x=avg_risk, line_dash="dash", line_color="gray", annotation_text="平均風險")
        
        st.plotly_chart(fig, width="stretch")
    
    # Tab 2: 權益曲線
    with tab2:
        st.subheader("權益曲線比較")
        
        fig = go.Figure()
        
        colors = ['blue', 'red', 'green', 'orange']
        
        for i, (strategy_name, data) in enumerate(strategies_data.items()):
            equity_df = data['equity']
            
            fig.add_trace(go.Scatter(
                x=equity_df['date'],
                y=equity_df['equity'],
                mode='lines',
                name=strategy_name,
                line=dict(width=2, color=colors[i])
            ))
        
        # 添加初始資金參考線
        initial_cash = strategies_data[selected_strategies[0]]['equity']['equity'].iloc[0]
        
        fig.add_hline(
            y=initial_cash,
            line_dash="dash",
            line_color="gray",
            annotation_text=f"初始資金: ${initial_cash:,.0f}"
        )
        
        fig.update_layout(
            title='權益曲線比較',
            xaxis_title='日期',
            yaxis_title='權益 ($)',
            height=600,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, width="stretch")
        
        # 報酬率比較
        st.markdown("### 累積報酬率比較")
        
        fig = go.Figure()
        
        for i, (strategy_name, data) in enumerate(strategies_data.items()):
            equity_df = data['equity']
            initial = equity_df['equity'].iloc[0]
            cumulative_return = (equity_df['equity'] / initial - 1) * 100
            
            fig.add_trace(go.Scatter(
                x=equity_df['date'],
                y=cumulative_return,
                mode='lines',
                name=strategy_name,
                line=dict(width=2, color=colors[i])
            ))
        
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        
        fig.update_layout(
            title='累積報酬率比較',
            xaxis_title='日期',
            yaxis_title='報酬率 (%)',
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, width="stretch")
    
    # Tab 3: 回撤分析
    with tab3:
        st.subheader("回撤分析")
        
        fig = make_subplots(
            rows=len(selected_strategies),
            cols=1,
            subplot_titles=[f"{name} 回撤" for name in selected_strategies],
            vertical_spacing=0.1
        )
        
        colors = ['blue', 'red', 'green', 'orange']
        
        for i, (strategy_name, data) in enumerate(strategies_data.items(), 1):
            equity_df = data['equity']
            
            # 計算回撤
            cummax = equity_df['equity'].cummax()
            drawdown = (equity_df['equity'] - cummax) / cummax * 100
            
            fig.add_trace(
                go.Scatter(
                    x=equity_df['date'],
                    y=drawdown,
                    fill='tozeroy',
                    name=strategy_name,
                    line=dict(color=colors[i-1]),
                    showlegend=False
                ),
                row=i, col=1
            )
            
            # 標記最大回撤點
            max_dd_idx = drawdown.idxmin()
            max_dd_date = equity_df.loc[max_dd_idx, 'date']
            max_dd_value = drawdown[max_dd_idx]
            
            fig.add_annotation(
                x=max_dd_date,
                y=max_dd_value,
                text=f"最大回撤: {max_dd_value:.2f}%",
                showarrow=True,
                arrowhead=2,
                row=i, col=1
            )
        
        fig.update_layout(
            height=300 * len(selected_strategies),
            hovermode='x unified'
        )
        
        fig.update_yaxes(title_text="回撤 (%)")
        
        st.plotly_chart(fig, width="stretch")
        
        # 回撤統計
        st.markdown("### 回撤統計")
        
        drawdown_stats = []
        
        for strategy_name, data in strategies_data.items():
            equity_df = data['equity']
            cummax = equity_df['equity'].cummax()
            drawdown = (equity_df['equity'] - cummax) / cummax * 100
            
            drawdown_stats.append({
                '策略': strategy_name,
                '最大回撤 (%)': f"{drawdown.min():.2f}",
                '平均回撤 (%)': f"{drawdown[drawdown < 0].mean():.2f}" if (drawdown < 0).any() else "0.00",
                '回撤天數': len(drawdown[drawdown < 0]),
                '回撤期數': f"{len(drawdown[drawdown < 0]) / len(drawdown) * 100:.1f}%"
            })
        
        dd_df = pd.DataFrame(drawdown_stats)
        st.dataframe(dd_df, width="stretch", hide_index=True)
    
    # Tab 4: 詳細指標
    with tab4:
        st.subheader("詳細績效指標")
        
        for strategy_name, data in strategies_data.items():
            with st.expander(f"📊 {strategy_name}", expanded=True):
                metrics = data['metrics']
                equity_df = data['equity']
                trades_df = data['trades']
                
                # 基本指標
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("總報酬率", f"{metrics['total_return']:.2f}%")
                    st.metric("年化報酬", f"{metrics['annual_return']:.2f}%")
                
                with col2:
                    st.metric("夏普比率", f"{metrics['sharpe_ratio']:.3f}")
                    st.metric("波動率", f"{metrics['volatility']:.2f}%")
                
                with col3:
                    st.metric("最大回撤", f"{metrics['max_drawdown']:.2f}%")
                    if metrics['win_rate'] is not None:
                        st.metric("勝率", f"{metrics['win_rate']:.2f}%")
                
                with col4:
                    if metrics['profit_factor'] is not None:
                        st.metric("獲利因子", f"{metrics['profit_factor']:.2f}")
                    if metrics['total_trades'] is not None:
                        st.metric("交易次數", metrics['total_trades'])
                
                # 交易記錄（如果有）
                if trades_df is not None and not trades_df.empty:
                    st.markdown("#### 交易記錄")
                    
                    # 顯示前 10 筆交易
                    display_df = trades_df.head(10).copy()
                    
                    # 格式化日期
                    if 'date' in display_df.columns:
                        display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
                    
                    st.dataframe(display_df, width="stretch", hide_index=True)
                    
                    # 下載完整交易記錄
                    csv = trades_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label=f"📥 下載 {strategy_name} 完整交易記錄",
                        data=csv,
                        file_name=f"{strategy_name.replace(' ', '_')}_trades.csv",
                        mime="text/csv",
                        key=f"download_{strategy_name}"
                    )
        
        # 總結建議
        st.markdown("---")
        st.markdown("### 💡 策略選擇建議")
        
        # 找出最佳策略
        best_return = max(strategies_data.items(), key=lambda x: x[1]['metrics']['annual_return'])
        best_sharpe = max(strategies_data.items(), key=lambda x: x[1]['metrics']['sharpe_ratio'])
        best_drawdown = min(strategies_data.items(), key=lambda x: abs(x[1]['metrics']['max_drawdown']))
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.success(f"**最高報酬: {best_return[0]}**")
            st.write(f"年化報酬: {best_return[1]['metrics']['annual_return']:.2f}%")
        
        with col2:
            st.success(f"**最佳風險調整: {best_sharpe[0]}**")
            st.write(f"夏普比率: {best_sharpe[1]['metrics']['sharpe_ratio']:.3f}")
        
        with col3:
            st.success(f"**最小回撤: {best_drawdown[0]}**")
            st.write(f"最大回撤: {best_drawdown[1]['metrics']['max_drawdown']:.2f}%")

if __name__ == '__main__':
    show()
