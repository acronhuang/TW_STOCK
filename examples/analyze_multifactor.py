#!/usr/bin/env python3
"""
多因子策略分析報告

對比分析多因子策略與其他策略的績效
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Dict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def analyze_strategy(equity_file: Path, trades_file: Path, strategy_name: str) -> Dict:
    """
    分析策略績效
    
    Args:
        equity_file: 權益曲線文件
        trades_file: 交易記錄文件
        strategy_name: 策略名稱
    
    Returns:
        績效指標字典
    """
    if not equity_file.exists():
        return None
    
    # 載入權益曲線
    equity_df = pd.read_csv(equity_file)
    equity_df['date'] = pd.to_datetime(equity_df['date'])
    
    # 基本指標
    initial_value = equity_df['equity'].iloc[0]
    final_value = equity_df['equity'].iloc[-1]
    total_return = (final_value / initial_value - 1) * 100
    
    # 日期範圍
    start_date = equity_df['date'].iloc[0]
    end_date = equity_df['date'].iloc[-1]
    days = (end_date - start_date).days
    years = days / 365.25
    
    # 年化報酬率
    annual_return = ((final_value / initial_value) ** (1 / years) - 1) * 100 if years > 0 else 0
    
    # 計算每日報酬率
    equity_df['returns'] = equity_df['equity'].pct_change()
    daily_returns = equity_df['returns'].dropna()
    
    # 夏普比率
    sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
    
    # 最大回撤
    equity_df['cummax'] = equity_df['equity'].cummax()
    equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
    max_drawdown = equity_df['drawdown'].min() * 100
    
    # 波動率
    volatility = daily_returns.std() * np.sqrt(252) * 100
    
    # 交易統計
    if trades_file.exists():
        trades_df = pd.read_csv(trades_file)
        total_trades = len(trades_df)
        
        if 'action' in trades_df.columns:
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            if len(sell_trades) > 0 and 'pnl' in sell_trades.columns:
                winning_trades = len(sell_trades[sell_trades['pnl'] > 0])
                win_rate = winning_trades / len(sell_trades) * 100
                
                avg_win = sell_trades[sell_trades['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
                avg_loss = abs(sell_trades[sell_trades['pnl'] < 0]['pnl'].mean()) if len(sell_trades) > winning_trades else 0
                profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
            else:
                win_rate = 0
                profit_factor = 0
        else:
            win_rate = 0
            profit_factor = 0
    else:
        total_trades = 0
        win_rate = 0
        profit_factor = 0
    
    return {
        '策略': strategy_name,
        '年化報酬率': annual_return,
        '總報酬率': total_return,
        '夏普比率': sharpe_ratio,
        '最大回撤': max_drawdown,
        '波動率': volatility,
        '勝率': win_rate,
        '盈虧比': profit_factor,
        '交易次數': total_trades,
        '回測天數': days
    }


def generate_report():
    """生成分析報告"""
    print("=" * 80)
    print("多因子策略分析報告")
    print("=" * 80)
    print()
    
    charts_dir = project_root / 'charts'
    
    # 策略配置
    strategies = [
        {
            'name': '多因子策略',
            'equity_file': charts_dir / 'multifactor_equity.csv',
            'trades_file': charts_dir / 'multifactor_trades.csv',
            'description': '結合動能、價值、質量 17 個因子的綜合選股策略'
        }
    ]
    
    # 分析所有策略
    results = []
    for strategy in strategies:
        metrics = analyze_strategy(
            strategy['equity_file'],
            strategy['trades_file'],
            strategy['name']
        )
        if metrics:
            results.append(metrics)
            print(f"✅ {strategy['name']}")
            print(f"   {strategy['description']}")
            print()
    
    if not results:
        print("❌ 找不到策略結果文件")
        return
    
    # 創建比較表
    df = pd.DataFrame(results)
    
    print("=" * 80)
    print("績效比較")
    print("=" * 80)
    print()
    
    # 格式化輸出
    display_df = df.copy()
    display_df['年化報酬率'] = display_df['年化報酬率'].apply(lambda x: f'{x:.2f}%')
    display_df['總報酬率'] = display_df['總報酬率'].apply(lambda x: f'{x:.2f}%')
    display_df['夏普比率'] = display_df['夏普比率'].apply(lambda x: f'{x:.3f}')
    display_df['最大回撤'] = display_df['最大回撤'].apply(lambda x: f'{x:.2f}%')
    display_df['波動率'] = display_df['波動率'].apply(lambda x: f'{x:.2f}%')
    display_df['勝率'] = display_df['勝率'].apply(lambda x: f'{x:.2f}%' if x > 0 else 'N/A')
    display_df['盈虧比'] = display_df['盈虧比'].apply(lambda x: f'{x:.2f}' if x > 0 else 'N/A')
    
    print(display_df.to_string(index=False))
    print()
    
    # 分析洞察
    print("=" * 80)
    print("分析洞察")
    print("=" * 80)
    print()
    
    best_return_idx = df['年化報酬率'].idxmax()
    best_sharpe_idx = df['夏普比率'].idxmax()
    best_drawdown_idx = df['最大回撤'].idxmax()  # 最大回撤是負數，所以最大值代表最小回撤
    
    print(f"🏆 最佳年化報酬率: {df.loc[best_return_idx, '策略']:20s} {df.loc[best_return_idx, '年化報酬率']:.2f}%")
    print(f"🏆 最佳夏普比率:   {df.loc[best_sharpe_idx, '策略']:20s} {df.loc[best_sharpe_idx, '夏普比率']:.3f}")
    print(f"🏆 最小最大回撤:   {df.loc[best_drawdown_idx, '策略']:20s} {df.loc[best_drawdown_idx, '最大回撤']:.2f}%")
    print()
    
    # 多因子策略的特點
    multifactor_metrics = df[df['策略'] == '多因子策略'].iloc[0]
    
    print("多因子策略特點分析:")
    print("-" * 80)
    print()
    print(f"✅ 年化報酬率 {multifactor_metrics['年化報酬率']:.2f}%")
    
    if multifactor_metrics['年化報酬率'] > 15:
        print("   → 表現優異，顯著超越市場平均（大盤年化約 8-10%）")
    elif multifactor_metrics['年化報酬率'] > 10:
        print("   → 表現良好，穩定超越市場")
    else:
        print("   → 表現平穩")
    print()
    
    print(f"✅ 夏普比率 {multifactor_metrics['夏普比率']:.3f}")
    if multifactor_metrics['夏普比率'] > 1.5:
        print("   → 風險調整後報酬極佳（>1.5 為優秀）")
    elif multifactor_metrics['夏普比率'] > 1.0:
        print("   → 風險調整後報酬良好（>1.0 為良好）")
    else:
        print("   → 風險調整後報酬一般")
    print()
    
    print(f"✅ 最大回撤 {multifactor_metrics['最大回撤']:.2f}%")
    if multifactor_metrics['最大回撤'] > -10:
        print("   → 風險控制優秀（回撤 <10%）")
    elif multifactor_metrics['最大回撤'] > -20:
        print("   → 風險控制良好（回撤 <20%）")
    else:
        print("   → 風險較高，需要改進")
    print()
    
    print(f"✅ 勝率 {multifactor_metrics['勝率']:.2f}%")
    if multifactor_metrics['勝率'] > 60:
        print("   → 交易勝率高，選股能力強")
    elif multifactor_metrics['勝率'] > 50:
        print("   → 交易勝率正常")
    else:
        print("   → 勝率需要改進")
    print()
    
    # 因子組合分析
    print("=" * 80)
    print("因子組合策略優勢")
    print("=" * 80)
    print()
    print("1. 多因子分散風險")
    print("   - 結合動能、價值、質量三大類因子")
    print("   - 動能因子捕捉市場趨勢")
    print("   - 價值因子挖掘低估標的")
    print("   - 質量因子確保財務健全")
    print()
    print("2. 量化選股客觀")
    print("   - 基於 17 個量化指標綜合評分")
    print("   - 排除主觀情緒干擾")
    print("   - 系統化決策流程")
    print()
    print("3. 定期調倉紀律")
    print("   - 每月重新評估持股")
    print("   - 及時淘汰落後標的")
    print("   - 持續優化組合配置")
    print()
    
    # 改進建議
    print("=" * 80)
    print("策略優化建議")
    print("=" * 80)
    print()
    print("1. 擴充數據覆蓋")
    print(f"   - 當前因子數據覆蓋: 動能 85%, 價值/質量 8%")
    print("   - 待財務報表數據完整後，價值與質量因子將發揮更大作用")
    print()
    print("2. 參數優化")
    print("   - 測試不同因子權重組合")
    print("   - 調整持股數量（當前 20 支）")
    print("   - 優化調倉頻率（當前每月）")
    print()
    print("3. 風險管理")
    print("   - 加入行業分散限制")
    print("   - 設置單股權重上限")
    print("   - 考慮市值等權重配置")
    print()
    print("4. 市場環境適應")
    print("   - 牛市增加動能權重")
    print("   - 熊市增加價值與質量權重")
    print("   - 動態調整因子配置")
    print()
    
    # 保存報告
    output_file = charts_dir / 'multifactor_analysis_report.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("多因子策略分析報告\n")
        f.write("=" * 80 + "\n\n")
        f.write("績效指標:\n")
        f.write("-" * 80 + "\n")
        for key, value in multifactor_metrics.items():
            if isinstance(value, float):
                if '率' in str(key) or '撤' in str(key):
                    f.write(f"{key:15s}: {value:8.2f}%\n")
                elif '比' in str(key):
                    f.write(f"{key:15s}: {value:8.3f}\n")
                else:
                    f.write(f"{key:15s}: {value:8.2f}\n")
            else:
                f.write(f"{key:15s}: {value}\n")
    
    print(f"💾 完整報告已保存: {output_file}")
    print()
    print("=" * 80)
    print("✅ 分析完成！")
    print("=" * 80)


if __name__ == '__main__':
    generate_report()
