#!/usr/bin/env python3
"""
多因子策略視覺化

生成策略績效圖表
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設置中文字體
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_equity_curve(equity_df: pd.DataFrame, output_path: Path):
    """
    繪製權益曲線
    
    Args:
        equity_df: 權益數據
        output_path: 輸出路徑
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # 權益曲線
    ax1.plot(equity_df['date'], equity_df['equity'], linewidth=2, color='#2E86AB', label='總權益')
    ax1.plot(equity_df['date'], equity_df['cash'], linewidth=1.5, color='#A23B72', alpha=0.7, linestyle='--', label='現金')
    ax1.plot(equity_df['date'], equity_df['market_value'], linewidth=1.5, color='#F18F01', alpha=0.7, linestyle='--', label='持股市值')
    
    # 標記起始點
    ax1.scatter(equity_df['date'].iloc[0], equity_df['equity'].iloc[0], 
                color='green', s=100, zorder=5, label='開始')
    ax1.scatter(equity_df['date'].iloc[-1], equity_df['equity'].iloc[-1], 
                color='red', s=100, zorder=5, label='結束')
    
    # 格式化
    ax1.set_title('多因子策略權益曲線 (2024)', fontsize=16, fontweight='bold', pad=20)
    ax1.set_xlabel('日期', fontsize=12)
    ax1.set_ylabel('權益 ($)', fontsize=12)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 添加績效文字
    initial = equity_df['equity'].iloc[0]
    final = equity_df['equity'].iloc[-1]
    total_return = (final / initial - 1) * 100
    
    textstr = f'初始: ${initial:,.0f}\n最終: ${final:,.0f}\n報酬: {total_return:.2f}%'
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax1.text(0.02, 0.98, textstr, transform=ax1.transAxes, fontsize=11,
             verticalalignment='top', bbox=props)
    
    # 回撤曲線
    equity_df['cummax'] = equity_df['equity'].cummax()
    equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
    
    ax2.fill_between(equity_df['date'], equity_df['drawdown'], 0, 
                     color='#C73E1D', alpha=0.5, label='回撤')
    ax2.plot(equity_df['date'], equity_df['drawdown'], linewidth=1.5, color='#C73E1D')
    
    # 標記最大回撤點
    max_dd_idx = equity_df['drawdown'].idxmin()
    max_dd_date = equity_df.loc[max_dd_idx, 'date']
    max_dd_value = equity_df.loc[max_dd_idx, 'drawdown']
    ax2.scatter(max_dd_date, max_dd_value, color='red', s=100, zorder=5)
    ax2.annotate(f'最大回撤: {max_dd_value:.2f}%', 
                xy=(max_dd_date, max_dd_value),
                xytext=(10, -30), textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
    
    ax2.set_title('回撤分析', fontsize=14, fontweight='bold', pad=15)
    ax2.set_xlabel('日期', fontsize=12)
    ax2.set_ylabel('回撤 (%)', fontsize=12)
    ax2.legend(loc='lower left', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 權益曲線圖已保存: {output_path}")
    plt.close()


def plot_monthly_returns(equity_df: pd.DataFrame, output_path: Path):
    """
    繪製月度報酬
    
    Args:
        equity_df: 權益數據
        output_path: 輸出路徑
    """
    # 計算月度報酬
    equity_df['month'] = equity_df['date'].dt.to_period('M')
    monthly = equity_df.groupby('month').agg({
        'equity': ['first', 'last']
    }).reset_index()
    monthly.columns = ['month', 'start', 'end']
    monthly['return'] = (monthly['end'] / monthly['start'] - 1) * 100
    monthly['month_str'] = monthly['month'].astype(str)
    
    # 繪圖
    fig, ax = plt.subplots(figsize=(12, 6))
    
    colors = ['#2E86AB' if r > 0 else '#C73E1D' for r in monthly['return']]
    bars = ax.bar(monthly['month_str'], monthly['return'], color=colors, alpha=0.7, edgecolor='black')
    
    # 添加數值標籤
    for bar, value in zip(bars, monthly['return']):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{value:.1f}%',
                ha='center', va='bottom' if height > 0 else 'top',
                fontsize=9, fontweight='bold')
    
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax.set_title('多因子策略月度報酬 (2024)', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('月份', fontsize=12)
    ax.set_ylabel('報酬率 (%)', fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')
    plt.xticks(rotation=45, ha='right')
    
    # 統計信息
    positive = len(monthly[monthly['return'] > 0])
    total = len(monthly)
    avg_return = monthly['return'].mean()
    
    textstr = f'正報酬月份: {positive}/{total} ({positive/total*100:.1f}%)\n平均月報酬: {avg_return:.2f}%'
    props = dict(boxstyle='round', facecolor='lightblue', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 月度報酬圖已保存: {output_path}")
    plt.close()


def plot_returns_distribution(equity_df: pd.DataFrame, output_path: Path):
    """
    繪製報酬分布
    
    Args:
        equity_df: 權益數據
        output_path: 輸出路徑
    """
    # 計算日報酬率
    equity_df['daily_return'] = equity_df['equity'].pct_change() * 100
    returns = equity_df['daily_return'].dropna()
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # 直方圖
    ax1.hist(returns, bins=50, color='#2E86AB', alpha=0.7, edgecolor='black')
    ax1.axvline(returns.mean(), color='red', linestyle='--', linewidth=2, label=f'平均: {returns.mean():.3f}%')
    ax1.axvline(0, color='black', linestyle='-', linewidth=1)
    
    ax1.set_title('日報酬率分布', fontsize=14, fontweight='bold', pad=15)
    ax1.set_xlabel('日報酬率 (%)', fontsize=12)
    ax1.set_ylabel('頻率', fontsize=12)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # 統計
    textstr = f'平均: {returns.mean():.3f}%\n標準差: {returns.std():.3f}%\n最大: {returns.max():.2f}%\n最小: {returns.min():.2f}%'
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax1.text(0.02, 0.98, textstr, transform=ax1.transAxes, fontsize=10,
             verticalalignment='top', bbox=props)
    
    # QQ圖 (簡化版 - 排序後的報酬 vs 正態分布分位數)
    sorted_returns = np.sort(returns)
    theoretical_quantiles = np.random.normal(returns.mean(), returns.std(), len(returns))
    theoretical_quantiles.sort()
    
    ax2.scatter(theoretical_quantiles, sorted_returns, alpha=0.5, s=20)
    
    # 45度參考線
    min_val = min(theoretical_quantiles.min(), sorted_returns.min())
    max_val = max(theoretical_quantiles.max(), sorted_returns.max())
    ax2.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2, label='理想常態分布')
    
    ax2.set_title('Q-Q 圖 (常態分布檢驗)', fontsize=14, fontweight='bold', pad=15)
    ax2.set_xlabel('理論分位數', fontsize=12)
    ax2.set_ylabel('實際分位數', fontsize=12)
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ 報酬分布圖已保存: {output_path}")
    plt.close()


def main():
    """主函數"""
    print("=" * 80)
    print("多因子策略視覺化")
    print("=" * 80)
    print()
    
    charts_dir = project_root / 'charts'
    equity_file = charts_dir / 'multifactor_equity.csv'
    
    if not equity_file.exists():
        print(f"❌ 找不到權益曲線文件: {equity_file}")
        print("請先運行 backtest_multifactor.py")
        return
    
    # 載入數據
    equity_df = pd.read_csv(equity_file)
    equity_df['date'] = pd.to_datetime(equity_df['date'])
    
    print(f"📊 載入數據: {len(equity_df)} 條記錄")
    print(f"期間: {equity_df['date'].iloc[0].date()} ~ {equity_df['date'].iloc[-1].date()}")
    print()
    
    # 生成圖表
    print("生成圖表...")
    print("-" * 80)
    
    # 1. 權益曲線與回撤
    plot_equity_curve(equity_df, charts_dir / 'multifactor_equity_curve.png')
    
    # 2. 月度報酬
    plot_monthly_returns(equity_df, charts_dir / 'multifactor_monthly_returns.png')
    
    # 3. 報酬分布
    plot_returns_distribution(equity_df, charts_dir / 'multifactor_returns_distribution.png')
    
    print()
    print("=" * 80)
    print("✅ 所有圖表已生成！")
    print()
    print("生成的圖表:")
    print(f"  1. {charts_dir / 'multifactor_equity_curve.png'}")
    print(f"  2. {charts_dir / 'multifactor_monthly_returns.png'}")
    print(f"  3. {charts_dir / 'multifactor_returns_distribution.png'}")
    print()
    print("💡 提示: 也可在 Dashboard (http://localhost:8502) 查看互動式圖表")
    print("=" * 80)


if __name__ == '__main__':
    main()
