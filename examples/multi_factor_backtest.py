#!/usr/bin/env python3
"""
多因子策略回測示例

結合因子庫與回測引擎，展示完整的量化投資工作流程:
1. 計算多個量化因子
2. 基於因子建立選股策略
3. 執行回測驗證策略效果
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.backtesting import Backtest
from src.backtesting.strategy import Strategy
from src.factors import FactorLibrary


class MultiFactorStrategy(Strategy):
    """
    多因子選股策略
    
    選股邏輯:
    1. 價值: 低 P/E, 低 P/B
    2. 動能: 正報酬, RSI 不過熱
    3. 質量: 高 ROE, 低負債
    
    綜合評分後選擇前 N 名股票
    """
    
    def __init__(self):
        super().__init__(name="Multi-Factor Strategy")
        self.factor_lib = None
        self.top_n = 3
        self.rebalance_days = 30
        self.last_rebalance = None
    
    def setup(self, top_n: int = 3, rebalance_days: int = 30):
        """
        設定策略參數
        
        Args:
            top_n: 選股數量
            rebalance_days: 調倉頻率（天）
        """
        self.top_n = top_n
        self.rebalance_days = rebalance_days
        self.factor_lib = FactorLibrary()
        self.params = {
            'top_n': top_n,
            'rebalance_days': rebalance_days
        }
    
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成交易信號
        
        策略:
        - 每 N 天調倉一次
        - 賣出不在 top N 的持倉
        - 買入 top N 股票
        """
        signals = {}
        
        # 檢查是否需要調倉
        if self.last_rebalance is not None:
            days_since_rebalance = (date - self.last_rebalance).days
            if days_since_rebalance < self.rebalance_days:
                # 未到調倉日，全部持有
                for symbol in data['symbol'].unique():
                    signals[symbol] = 'HOLD'
                return signals
        
        # 執行調倉
        self.last_rebalance = date
        
        # 取得當日所有股票的因子數據
        factors = self.factor_lib.get_cross_section(
            date=date.strftime('%Y-%m-%d'),
            factor_names=['pe_ratio', 'pb_ratio', 'return_3m', 'rsi_14', 'roe', 'debt_ratio']
        )
        
        if factors.empty:
            print(f"⚠️  {date.date()} 無因子數據")
            for symbol in data['symbol'].unique():
                signals[symbol] = 'HOLD'
            return signals
        
        # 移除缺失值
        factors = factors.dropna()
        
        if len(factors) < self.top_n:
            print(f"⚠️  {date.date()} 有效股票不足 {self.top_n} 支")
            for symbol in data['symbol'].unique():
                signals[symbol] = 'HOLD'
            return signals
        
        # 計算綜合評分
        factors['value_score'] = self._normalize_factor(factors['pe_ratio'], lower_is_better=True)
        factors['value_score'] += self._normalize_factor(factors['pb_ratio'], lower_is_better=True)
        
        factors['momentum_score'] = self._normalize_factor(factors['return_3m'], lower_is_better=False)
        factors['momentum_score'] += self._normalize_factor(factors['rsi_14'], target_range=(30, 70))
        
        factors['quality_score'] = self._normalize_factor(factors['roe'], lower_is_better=False)
        factors['quality_score'] += self._normalize_factor(factors['debt_ratio'], lower_is_better=True)
        
        # 總評分（等權重）
        factors['total_score'] = (
            factors['value_score'] + 
            factors['momentum_score'] + 
            factors['quality_score']
        )
        
        # 選擇 top N
        top_stocks = factors.nlargest(self.top_n, 'total_score')['symbol'].tolist()
        
        print(f"📊 {date.date()} 調倉: {', '.join(top_stocks)}")
        
        # 生成信號
        for symbol in data['symbol'].unique():
            if symbol in top_stocks:
                signals[symbol] = 'BUY'
            else:
                signals[symbol] = 'SELL'
        
        return signals
    
    def _normalize_factor(self, series: pd.Series, lower_is_better: bool = False, 
                         target_range: tuple = None) -> pd.Series:
        """
        正規化因子值到 0-1 範圍
        
        Args:
            series: 因子序列
            lower_is_better: True 表示值越低越好（如 P/E）
            target_range: 目標範圍（如 RSI 的 30-70）
        
        Returns:
            正規化後的評分
        """
        if target_range:
            # 對於有目標範圍的因子（如 RSI）
            low, high = target_range
            score = pd.Series(index=series.index, dtype=float)
            score[series < low] = (series[series < low] - low).abs()  # 超賣扣分
            score[series > high] = (series[series > high] - high).abs()  # 超買扣分
            score[(series >= low) & (series <= high)] = 1.0  # 在範圍內給滿分
            return 1 - (score / score.max())  # 反轉讓高分變好
        
        # 標準化到 0-1
        min_val = series.min()
        max_val = series.max()
        
        if max_val == min_val:
            return pd.Series(0.5, index=series.index)
        
        normalized = (series - min_val) / (max_val - min_val)
        
        if lower_is_better:
            normalized = 1 - normalized
        
        return normalized


def main():
    print("="*80)
    print("多因子策略回測示例")
    print("="*80)
    print()
    
    # 步驟 1: 準備因子數據
    print("【步驟 1】準備因子數據")
    print("-" * 80)
    
    factor_lib = FactorLibrary()
    
    symbols = ['2330', '2317', '2454', '2412', '2308', '3008']  # 前幾大權值股
    start_date = '2024-01-01'
    end_date = '2024-12-31'
    
    print(f"股票池: {', '.join(symbols)}")
    print(f"期間: {start_date} ~ {end_date}")
    print()
    
    # 計算因子（如果尚未計算）
    print("確保因子數據完整...")
    stats = factor_lib.calculate_and_store(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        factor_types=['value', 'momentum', 'quality']
    )
    
    print(f"✅ 因子數據準備完成 (處理 {stats['processed']} 筆)")
    print()
    
    # 步驟 2: 建立多因子策略
    print("【步驟 2】建立多因子策略")
    print("-" * 80)
    
    strategy = MultiFactorStrategy()
    strategy.setup(
        top_n=3,  # 每次持有 3 支股票
        rebalance_days=30  # 每月調倉
    )
    
    print(f"策略: {strategy.name}")
    print(f"參數: {strategy.params}")
    print()
    
    # 步驟 3: 執行回測
    print("【步驟 3】執行回測")
    print("-" * 80)
    
    backtest = Backtest(
        strategy=strategy,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_cash=1_000_000,
        position_size=0.33,  # 持有 3 支，每支 33%
        commission_rate=0.003
    )
    
    results = backtest.run()
    
    # 步驟 4: 分析結果
    print()
    print("【步驟 4】績效分析")
    print("-" * 80)
    print(results['metrics'])
    
    # 匯出結果
    print()
    print("【匯出結果】")
    print("-" * 80)
    
    output_dir = project_root / "charts"
    output_dir.mkdir(exist_ok=True)
    
    # 權益曲線
    try:
        chart_path = output_dir / "multi_factor_equity_curve.png"
        backtest.plot_equity_curve(save_path=str(chart_path))
        print(f"✅ 權益曲線: {chart_path}")
    except:
        print("⚠️  無法繪製權益曲線（需要 matplotlib）")
    
    # 權益數據
    equity_file = output_dir / "multi_factor_equity.csv"
    results['equity_curve'].to_csv(equity_file, index=False)
    print(f"✅ 權益數據: {equity_file}")
    
    # 交易記錄
    trades_file = output_dir / "multi_factor_trades.csv"
    trades_df = pd.DataFrame([{
        'date': t.date,
        'symbol': t.symbol,
        'action': t.action,
        'shares': t.shares,
        'price': t.price,
        'commission': t.commission
    } for t in results['trades']])
    trades_df.to_csv(trades_file, index=False)
    print(f"✅ 交易記錄: {trades_file}")
    
    print()
    print("="*80)
    print("多因子策略回測完成！")
    print("="*80)

if __name__ == "__main__":
    main()
