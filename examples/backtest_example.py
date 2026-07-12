#!/usr/bin/env python3
"""
回測引擎示例 - 均線交叉策略回測

展示如何使用回測引擎進行策略驗證
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backtesting import Backtest
from src.backtesting.strategy import MovingAverageCrossover

def main():
    print("="*80)
    print("回測引擎示例 - 均線交叉策略")
    print("="*80)
    print()
    
    # 建立策略
    strategy = MovingAverageCrossover()
    strategy.setup(short_window=5, long_window=20)
    
    print(f"策略: {strategy.name}")
    print(f"參數: {strategy.params}")
    print()
    
    # 建立回測
    backtest = Backtest(
        strategy=strategy,
        symbols=['2330', '2317', '2454', '0050'],  # 台積電、鴻海、聯發科、元大台灣50
        start_date='2024-01-01',
        end_date='2024-12-31',
        initial_cash=1_000_000,  # 初始資金 100 萬
        position_size=0.25,  # 單筆倉位 25%
        commission_rate=0.003  # 手續費 0.3%
    )
    
    # 執行回測
    print("開始執行回測...")
    print()
    
    results = backtest.run()
    
    # 顯示績效指標
    print()
    print(results['metrics'])
    
    # 顯示交易記錄摘要
    trades = results['trades']
    print(f"\n交易記錄（前 10 筆）:")
    print("-" * 80)
    for i, trade in enumerate(trades[:10], 1):
        print(f"{i}. {trade.date.date()} | {trade.action:4s} | {trade.symbol} | "
              f"{trade.shares:6d} 股 @ {trade.price:7.2f} | "
              f"手續費 {trade.commission:.2f}")
    
    if len(trades) > 10:
        print(f"... 更多 {len(trades) - 10} 筆交易")
    
    # 繪製權益曲線
    print("\n繪製權益曲線...")
    try:
        chart_path = project_root / "charts" / "backtest_equity_curve.png"
        chart_path.parent.mkdir(exist_ok=True)
        backtest.plot_equity_curve(save_path=str(chart_path))
        print(f"✅ 權益曲線已儲存: {chart_path}")
    except Exception as e:
        print(f"⚠️  無法繪製圖表: {e}")
        print("提示: 請安裝 matplotlib (pip install matplotlib)")
    
    # 匯出結果
    output_path = project_root / "charts" / "backtest_results.csv"
    equity_df = results['equity_curve']
    equity_df.to_csv(output_path, index=False)
    print(f"✅ 權益曲線數據已匯出: {output_path}")
    
    print("\n" + "="*80)
    print("回測完成！")
    print("="*80)

if __name__ == "__main__":
    main()
