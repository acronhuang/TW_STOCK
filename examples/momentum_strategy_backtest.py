#!/usr/bin/env python3
"""
動能策略回測示例

策略邏輯:
- 使用動能因子 (return_3m, rsi_14) 選股
- 每月調倉一次
- 選取動能最強的前 3 支股票
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backtesting import Backtest, Strategy
from src.factors import FactorLibrary
import pandas as pd
from loguru import logger


class MomentumStrategy(Strategy):
    """
    純動能策略
    
    使用 3 個月報酬率和 RSI 指標選股
    - 高報酬率（動能強）
    - RSI 適中（避免過度買入或賣出）
    """
    
    def __init__(self):
        super().__init__(name="Momentum Strategy")
        self.factor_lib = FactorLibrary()
        self.top_n = 3
        self.rebalance_days = 30
        self.last_rebalance = None
        
    def setup(self, **kwargs):
        """初始化策略參數"""
        self.top_n = kwargs.get('top_n', 3)
        self.rebalance_days = kwargs.get('rebalance_days', 30)
        logger.info(f"策略參數: top_n={self.top_n}, rebalance_days={self.rebalance_days}")
        
    def generate_signals(self, date, data):
        """
        生成交易信號
        
        Returns:
            Dict[str, str]: {股票代碼: 信號} 其中信號為 'BUY'/'SELL'/'HOLD'
        """
        # 檢查是否需要調倉
        if self.last_rebalance and (date - self.last_rebalance).days < self.rebalance_days:
            return {symbol: 'HOLD' for symbol in data['symbol'].unique()}
        
        self.last_rebalance = date
        
        # 獲取所有股票的動能因子
        try:
            factors = self.factor_lib.get_cross_section(
                date=date.strftime('%Y-%m-%d'),
                factor_names=['return_3m', 'rsi_14']
            )
        except Exception as e:
            logger.warning(f"⚠️  {date.date()} 無法獲取因子數據: {e}")
            return {symbol: 'HOLD' for symbol in data['symbol'].unique()}
        
        if factors.empty:
            logger.warning(f"⚠️  {date.date()} 因子數據為空")
            return {symbol: 'HOLD' for symbol in data['symbol'].unique()}
        
        # 只保留有完整數據的股票
        factors = factors.dropna(subset=['return_3m', 'rsi_14'])
        
        if len(factors) < self.top_n:
            logger.warning(f"⚠️  {date.date()} 有效股票不足 {self.top_n} 支 (僅 {len(factors)} 支)")
            return {symbol: 'HOLD' for symbol in data['symbol'].unique()}
        
        # 計算動能評分
        # 1. 3 個月報酬率標準化（越高越好）
        factors['return_score'] = self._normalize(factors['return_3m'], lower_is_better=False)
        
        # 2. RSI 評分（prefer 40-60 range，避免極端值）
        factors['rsi_score'] = factors['rsi_14'].apply(lambda x: 
            1.0 if 40 <= x <= 60 else 
            0.8 if 30 <= x <= 70 else 
            0.5
        )
        
        # 3. 總分（加權平均）
        factors['total_score'] = factors['return_score'] * 0.7 + factors['rsi_score'] * 0.3
        
        # 選取評分最高的前 N 支股票
        top_stocks = factors.nlargest(self.top_n, 'total_score')
        
        logger.info(f"📊 {date.date()} 調倉:")
        for _, row in top_stocks.iterrows():
            logger.info(f"  - {row['symbol']}: 3M報酬={row['return_3m']:.2f}%, RSI={row['rsi_14']:.1f}, 評分={row['total_score']:.3f}")
        
        # 生成交易信號
        signals = {}
        for symbol in data['symbol'].unique():
            if symbol in top_stocks['symbol'].values:
                signals[symbol] = 'BUY'
            else:
                signals[symbol] = 'SELL'
        
        return signals
    
    def _normalize(self, series, lower_is_better=False):
        """標準化因子到 0-1 區間"""
        if series.empty or series.std() == 0:
            return pd.Series([0.5] * len(series), index=series.index)
        
        normalized = (series - series.min()) / (series.max() - series.min())
        if lower_is_better:
            normalized = 1 - normalized
        return normalized


def main():
    print("=" * 80)
    print("動能策略回測示例")
    print("=" * 80)
    
    # 步驟 1: 準備因子數據
    print("\n【步驟 1】準備因子數據")
    print("-" * 80)
    
    symbols = ['2330', '2317', '2454', '2412', '2308', '3008']
    start_date = '2024-01-01'
    end_date = '2024-12-31'
    
    print(f"股票池: {', '.join(symbols)}")
    print(f"期間: {start_date} ~ {end_date}")
    
    factor_lib = FactorLibrary()
    
    # 確保因子數據已計算
    print("\n檢查因子數據...")
    sample = factor_lib.get_factors(symbols[0], start_date, end_date)
    if sample.empty:
        print("⚠️  因子數據不存在，開始計算...")
        stats = factor_lib.calculate_and_store(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            factor_types=['momentum']
        )
        print(f"✅ 因子數據準備完成 {stats}")
    else:
        print(f"✅ 因子數據已存在 ({len(sample)} 筆)")
    
    # 步驟 2: 建立動能策略
    print("\n【步驟 2】建立動能策略")
    print("-" * 80)
    
    strategy = MomentumStrategy()
    strategy.setup(top_n=3, rebalance_days=30)
    
    print(f"策略: {strategy.name}")
    print(f"參數: top_n=3 (持有前3強), rebalance_days=30 (每月調倉)")
    
    # 步驟 3: 執行回測
    print("\n【步驟 3】執行回測")
    print("-" * 80)
    
    backtest = Backtest(
        strategy=strategy,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_cash=1_000_000,  # 100 萬
        position_size=0.33,  # 每支股票 33% (3 支共 100%)
        commission_rate=0.003  # 0.3% 手續費
    )
    
    results = backtest.run()
    
    # 步驟 4: 績效分析
    print("\n【步驟 4】績效分析")
    print("-" * 80)
    
    metrics = results['metrics']
    
    print("\n績效報告")
    print("=" * 60)
    print(f"報酬指標:")
    print(f"  總報酬率: {metrics.total_return:.2f}%")
    print(f"  年化報酬率: {metrics.annualized_return:.2f}%")
    
    print(f"\n風險指標:")
    print(f"  波動率（年化）: {metrics.volatility:.2f}%")
    print(f"  最大回撤: {metrics.max_drawdown:.2f}%")
    print(f"  最大回撤持續: {metrics.max_drawdown_duration} 天")
    
    print(f"\n風險調整報酬:")
    print(f"  夏普比率: {metrics.sharpe_ratio:.3f}")
    print(f"  Sortino Ratio: {metrics.sortino_ratio:.3f}")
    print(f"  Calmar Ratio: {metrics.calmar_ratio:.3f}")
    
    print(f"\n交易統計:")
    print(f"  總交易次數: {metrics.total_trades}")
    print(f"  獲利交易: {metrics.winning_trades}")
    print(f"  虧損交易: {metrics.losing_trades}")
    print(f"  勝率: {metrics.win_rate:.2f}%")
    
    print(f"\n獲利分析:")
    print(f"  平均獲利: {metrics.avg_win:.2f}")
    print(f"  平均虧損: {metrics.avg_loss:.2f}")
    print(f"  獲利因子: {metrics.profit_factor:.3f}")
    
    print(f"\n回測期間:")
    print(f"  開始日期: {metrics.start_date}")
    print(f"  結束日期: {metrics.end_date}")
    print(f"  交易天數: {metrics.trading_days}")
    print("=" * 60)
    
    # 顯示交易記錄
    trades = results['trades']
    if trades:
        print(f"\n交易記錄（共 {len(trades)} 筆）:")
        print("-" * 80)
        for i, trade in enumerate(trades[:20], 1):  # 顯示前 20 筆
            print(f"{i:2d}. {trade.date.date()} | {trade.action:4s} | {trade.symbol} | "
                  f"{trade.shares:5d} 股 @ {trade.price:7.2f} | 手續費 {trade.commission:.2f}")
        if len(trades) > 20:
            print(f"... 更多 {len(trades) - 20} 筆交易")
    
    # 步驟 5: 匯出結果
    print("\n【步驟 5】匯出結果")
    print("-" * 80)
    
    # 繪製權益曲線
    output_dir = project_root / 'charts'
    output_dir.mkdir(exist_ok=True)
    
    equity_chart = output_dir / 'momentum_equity_curve.png'
    backtest.plot_equity_curve(save_path=str(equity_chart))
    print(f"✅ 權益曲線: {equity_chart}")
    
    # 匯出權益數據
    equity_csv = output_dir / 'momentum_equity.csv'
    results['equity_curve'].to_csv(equity_csv, index=False)
    print(f"✅ 權益數據: {equity_csv}")
    
    # 匯出交易記錄
    trades_csv = output_dir / 'momentum_trades.csv'
    trades_df = pd.DataFrame([{
        'date': t.date,
        'symbol': t.symbol,
        'action': t.action,
        'shares': t.shares,
        'price': t.price,
        'commission': t.commission
    } for t in trades])
    trades_df.to_csv(trades_csv, index=False)
    print(f"✅ 交易記錄: {trades_csv}")
    
    print("\n" + "=" * 80)
    print("動能策略回測完成！")
    print("=" * 80)
    
    # 策略評估
    print("\n【策略評估】")
    print("-" * 80)
    
    if metrics.sharpe_ratio > 1.5:
        print("🎉 優秀！夏普比率 > 1.5，風險調整後報酬表現出色")
    elif metrics.sharpe_ratio > 1.0:
        print("✅ 良好！夏普比率 > 1.0，策略具有正向價值")
    elif metrics.sharpe_ratio > 0.5:
        print("⚠️  普通。夏普比率 > 0.5，策略有改進空間")
    else:
        print("❌ 不佳。夏普比率 < 0.5，建議調整策略")
    
    if abs(metrics.max_drawdown) < 10:
        print("✅ 風險控制優秀！最大回撤 < 10%")
    elif abs(metrics.max_drawdown) < 20:
        print("⚠️  風險控制尚可。最大回撤 < 20%")
    else:
        print("❌ 風險較高！最大回撤 > 20%，建議加強風險管理")
    
    if metrics.win_rate > 60:
        print(f"✅ 勝率優秀！{metrics.win_rate:.1f}% > 60%")
    elif metrics.win_rate > 50:
        print(f"⚠️  勝率尚可。{metrics.win_rate:.1f}% > 50%")
    else:
        print(f"❌ 勝率偏低。{metrics.win_rate:.1f}% < 50%")


if __name__ == '__main__':
    main()
