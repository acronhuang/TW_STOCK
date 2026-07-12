#!/usr/bin/env python3
"""
Performance Metrics 模組 - 績效指標計算

計算回測績效指標:
- 總報酬、年化報酬
- 夏普比率（Sharpe Ratio）
- 最大回撤（Maximum Drawdown）
- 勝率、獲利因子
- Calmar Ratio, Sortino Ratio
"""

import numpy as np
import pandas as pd
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class PerformanceMetrics:
    """績效指標數據類"""
    
    # 報酬指標
    total_return: float  # 總報酬率 (%)
    annualized_return: float  # 年化報酬率 (%)
    
    # 風險指標
    volatility: float  # 波動率 (年化標準差, %)
    max_drawdown: float  # 最大回撤 (%)
    max_drawdown_duration: int  # 最大回撤持續天數
    
    # 風險調整報酬
    sharpe_ratio: float  # 夏普比率
    sortino_ratio: float  # Sortino Ratio（只考慮下檔風險）
    calmar_ratio: float  # Calmar Ratio（年化報酬 / 最大回撤）
    
    # 交易統計
    total_trades: int  # 總交易次數
    winning_trades: int  # 獲利交易次數
    losing_trades: int  # 虧損交易次數
    win_rate: float  # 勝率 (%)
    
    # 獲利指標
    avg_win: float  # 平均獲利
    avg_loss: float  # 平均虧損
    profit_factor: float  # 獲利因子（總獲利 / 總虧損）
    
    # 時間統計
    start_date: str
    end_date: str
    trading_days: int
    
    def to_dict(self) -> Dict:
        """轉為字典"""
        return {
            'total_return': round(self.total_return, 2),
            'annualized_return': round(self.annualized_return, 2),
            'volatility': round(self.volatility, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_duration': self.max_drawdown_duration,
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'sortino_ratio': round(self.sortino_ratio, 3),
            'calmar_ratio': round(self.calmar_ratio, 3),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 2),
            'avg_win': round(self.avg_win, 2),
            'avg_loss': round(self.avg_loss, 2),
            'profit_factor': round(self.profit_factor, 3),
            'start_date': self.start_date,
            'end_date': self.end_date,
            'trading_days': self.trading_days
        }
    
    def __repr__(self):
        return f"""
績效報告
{'='*60}
報酬指標:
  總報酬率: {self.total_return:.2f}%
  年化報酬率: {self.annualized_return:.2f}%

風險指標:
  波動率（年化）: {self.volatility:.2f}%
  最大回撤: {self.max_drawdown:.2f}%
  最大回撤持續: {self.max_drawdown_duration} 天

風險調整報酬:
  夏普比率: {self.sharpe_ratio:.3f}
  Sortino Ratio: {self.sortino_ratio:.3f}
  Calmar Ratio: {self.calmar_ratio:.3f}

交易統計:
  總交易次數: {self.total_trades}
  獲利交易: {self.winning_trades}
  虧損交易: {self.losing_trades}
  勝率: {self.win_rate:.2f}%

獲利分析:
  平均獲利: {self.avg_win:.2f}
  平均虧損: {self.avg_loss:.2f}
  獲利因子: {self.profit_factor:.3f}

回測期間:
  開始日期: {self.start_date}
  結束日期: {self.end_date}
  交易天數: {self.trading_days}
{'='*60}
"""


class PerformanceCalculator:
    """績效計算器"""
    
    @staticmethod
    def calculate(equity_curve: List[Dict], trades: List, 
                  initial_cash: float, risk_free_rate: float = 0.01) -> PerformanceMetrics:
        """
        計算完整績效指標
        
        Args:
            equity_curve: 權益曲線 [{date, equity, ...}]
            trades: 交易記錄
            initial_cash: 初始資金
            risk_free_rate: 無風險利率（年化，default: 1%）
        
        Returns:
            PerformanceMetrics 物件
        """
        if not equity_curve:
            raise ValueError("權益曲線為空")
        
        # 轉為 DataFrame
        df = pd.DataFrame(equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 基本資訊
        start_date = df['date'].iloc[0].strftime('%Y-%m-%d')
        end_date = df['date'].iloc[-1].strftime('%Y-%m-%d')
        trading_days = len(df)
        
        # 計算日報酬率
        df['returns'] = df['equity'].pct_change()
        returns = df['returns'].dropna()
        
        # 報酬指標
        final_equity = df['equity'].iloc[-1]
        total_return = ((final_equity - initial_cash) / initial_cash) * 100
        
        # 年化報酬率（假設一年 252 個交易日）
        years = trading_days / 252
        if years > 0:
            annualized_return = (((final_equity / initial_cash) ** (1 / years)) - 1) * 100
        else:
            annualized_return = 0.0
        
        # 波動率（年化）
        if len(returns) > 1:
            daily_volatility = returns.std()
            volatility = daily_volatility * np.sqrt(252) * 100
        else:
            volatility = 0.0
        
        # 最大回撤
        max_dd, max_dd_duration = PerformanceCalculator._calculate_max_drawdown(df['equity'].values)
        
        # 夏普比率
        if volatility > 0:
            excess_return = annualized_return - (risk_free_rate * 100)
            sharpe_ratio = excess_return / volatility
        else:
            sharpe_ratio = 0.0
        
        # Sortino Ratio（只考慮下檔風險）
        negative_returns = returns[returns < 0]
        if len(negative_returns) > 1:
            downside_volatility = negative_returns.std() * np.sqrt(252) * 100
            if downside_volatility > 0:
                sortino_ratio = (annualized_return - (risk_free_rate * 100)) / downside_volatility
            else:
                sortino_ratio = 0.0
        else:
            sortino_ratio = 0.0
        
        # Calmar Ratio
        if abs(max_dd) > 0:
            calmar_ratio = annualized_return / abs(max_dd)
        else:
            calmar_ratio = 0.0
        
        # 交易統計
        trade_stats = PerformanceCalculator._analyze_trades(trades)
        
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            total_trades=trade_stats['total_trades'],
            winning_trades=trade_stats['winning_trades'],
            losing_trades=trade_stats['losing_trades'],
            win_rate=trade_stats['win_rate'],
            avg_win=trade_stats['avg_win'],
            avg_loss=trade_stats['avg_loss'],
            profit_factor=trade_stats['profit_factor'],
            start_date=start_date,
            end_date=end_date,
            trading_days=trading_days
        )
    
    @staticmethod
    def _calculate_max_drawdown(equity: np.ndarray) -> tuple:
        """
        計算最大回撤和持續時間
        
        Returns:
            (max_drawdown_pct, duration_days)
        """
        cummax = np.maximum.accumulate(equity)
        drawdown = (equity - cummax) / cummax * 100
        
        max_dd = drawdown.min()
        
        # 計算最大回撤持續時間
        max_dd_duration = 0
        current_duration = 0
        
        for dd in drawdown:
            if dd < 0:
                current_duration += 1
                max_dd_duration = max(max_dd_duration, current_duration)
            else:
                current_duration = 0
        
        return max_dd, max_dd_duration
    
    @staticmethod
    def _analyze_trades(trades: List) -> Dict:
        """
        分析交易統計
        
        Returns:
            交易統計字典
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0
            }
        
        # 將交易配對（買入-賣出）
        positions = {}  # {symbol: {'buy_price': price, 'buy_date': date, 'shares': shares}}
        completed_trades = []  # [{symbol, profit, profit_pct, holding_days}]
        
        for trade in trades:
            symbol = trade.symbol
            
            if trade.action == 'BUY':
                if symbol not in positions:
                    positions[symbol] = []
                positions[symbol].append({
                    'buy_price': trade.price,
                    'buy_date': trade.date,
                    'shares': trade.shares
                })
            
            elif trade.action == 'SELL' and symbol in positions:
                if not positions[symbol]:
                    continue
                
                # FIFO: 先買先賣
                buy_info = positions[symbol].pop(0)
                
                profit = (trade.price - buy_info['buy_price']) * trade.shares
                profit_pct = (profit / (buy_info['buy_price'] * trade.shares)) * 100
                holding_days = (trade.date - buy_info['buy_date']).days
                
                completed_trades.append({
                    'symbol': symbol,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'holding_days': holding_days
                })
        
        if not completed_trades:
            return {
                'total_trades': len(trades),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0
            }
        
        # 計算統計
        wins = [t['profit'] for t in completed_trades if t['profit'] > 0]
        losses = [t['profit'] for t in completed_trades if t['profit'] < 0]
        
        total_trades = len(completed_trades)
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0
        
        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else 0.0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor
        }
