"""
v2.1 整合策略回測腳本

功能:
1. 完整回測 v2.1 策略（2022-2024）
2. Walk-forward 測試（6 個月一期）
3. v2.0 vs v2.1 對比分析
4. 詳細績效報告

執行:
    python3 scripts/backtest_integrated_v21.py --start-date 2022-01-01 --end-date 2024-12-31

作者: Ming
創建日期: 2026-02-23
"""

import sys
sys.path.append('/home/mdsadmin/Stock/tw-stock-analysis/src')

import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from pymongo import MongoClient
import json
from tqdm import tqdm

from strategy.integrated_strategy_v21 import IntegratedStrategyV21
from strategy.multi_factor_strategy import MultiFactorStrategy


class BacktestV21:
    """v2.1 策略回測器"""
    
    def __init__(
        self,
        db_connection,
        initial_capital: float = 10_000_000,
        rebalance_frequency: str = 'monthly'
    ):
        """
        初始化
        
        Args:
            db_connection: MongoDB 連接
            initial_capital: 初始資金
            rebalance_frequency: 再平衡頻率 ('monthly' / 'weekly')
        """
        self.db = db_connection
        self.initial_capital = initial_capital
        self.rebalance_frequency = rebalance_frequency
        
        # 初始化策略
        self.strategy_v21 = IntegratedStrategyV21(db_connection)
        self.strategy_v20 = MultiFactorStrategy(db_connection)
        
        # 回測狀態
        self.capital = initial_capital
        self.positions = {}  # {stock_id: {'shares': 1000, 'entry_price': 580, 'entry_date': '2024-01-01'}}
        self.trades = []
        self.daily_portfolio_values = []
    
    def get_rebalance_dates(
        self,
        start_date: str,
        end_date: str
    ) -> List[str]:
        """
        獲取再平衡日期
        
        Args:
            start_date: 開始日期
            end_date: 結束日期
        
        Returns:
            再平衡日期列表
        """
        dates = []
        current = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        if self.rebalance_frequency == 'monthly':
            # 每月第一個交易日
            while current <= end:
                # 找到該月第一個有數據的交易日
                trading_day = self._find_next_trading_day(current.strftime('%Y-%m-%d'))
                if trading_day:
                    dates.append(trading_day)
                
                # 移到下個月
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
        
        return dates
    
    def _find_next_trading_day(self, date: str) -> str:
        """找到下一個交易日"""
        current = pd.to_datetime(date)
        
        for i in range(10):  # 最多往後找 10 天
            check_date = (current + timedelta(days=i)).strftime('%Y-%m-%d')
            
            # 檢查是否有交易數據
            has_data = self.db['stock_price'].find_one({
                'date': check_date
            })
            
            if has_data:
                return check_date
        
        return None
    
    def get_price(self, stock_id: str, date: str) -> float:
        """獲取股價"""
        data = self.db['stock_price'].find_one({
            'stock_id': stock_id,
            'date': date
        })
        
        return data['close'] if data else None
    
    def rebalance(self, date: str, selections: List):
        """
        再平衡持倉
        
        Args:
            date: 再平衡日期
            selections: 選股結果（StockRanking 列表）
        """
        # 1. 賣出不在新名單中的持倉
        current_holdings = list(self.positions.keys())
        new_holdings = [s.stock_id for s in selections]
        
        for stock_id in current_holdings:
            if stock_id not in new_holdings:
                # 賣出
                position = self.positions[stock_id]
                sell_price = self.get_price(stock_id, date)
                
                if sell_price:
                    sell_value = position['shares'] * sell_price
                    self.capital += sell_value
                    
                    # 記錄交易
                    self.trades.append({
                        'date': date,
                        'stock_id': stock_id,
                        'action': 'sell',
                        'price': sell_price,
                        'shares': position['shares'],
                        'value': sell_value,
                        'return_pct': (sell_price - position['entry_price']) / position['entry_price']
                    })
                    
                    del self.positions[stock_id]
        
        # 2. 買入新名單中的股票
        for selection in selections:
            stock_id = selection.stock_id
            target_weight = selection.position_weight
            buy_price = self.get_price(stock_id, date)
            
            if not buy_price:
                continue
            
            # 計算目標倉位
            target_value = self.capital * target_weight
            target_shares = int(target_value / buy_price / 1000) * 1000  # 整張
            
            if target_shares > 0:
                buy_value = target_shares * buy_price
                self.capital -= buy_value
                
                # 記錄交易
                self.trades.append({
                    'date': date,
                    'stock_id': stock_id,
                    'action': 'buy',
                    'price': buy_price,
                    'shares': target_shares,
                    'value': buy_value,
                    'weight': target_weight
                })
                
                # 更新持倉
                self.positions[stock_id] = {
                    'shares': target_shares,
                    'entry_price': buy_price,
                    'entry_date': date
                }
    
    def check_daily_exits(self, date: str):
        """
        每日檢查出場訊號
        
        Args:
            date: 當前日期
        """
        if not self.positions:
            return
        
        # 準備持倉資訊
        holdings = [
            {
                'stock_id': stock_id,
                'entry_price': pos['entry_price'],
                'entry_date': pos['entry_date']
            }
            for stock_id, pos in self.positions.items()
        ]
        
        # 檢查出場訊號
        exit_signals = self.strategy_v21.check_exit_signals(holdings, date)
        
        # 執行出場
        for signal in exit_signals:
            if signal.should_exit:
                stock_id = signal.stock_id
                position = self.positions[stock_id]
                
                sell_value = position['shares'] * signal.current_price
                self.capital += sell_value
                
                # 記錄交易
                self.trades.append({
                    'date': date,
                    'stock_id': stock_id,
                    'action': 'sell',
                    'price': signal.current_price,
                    'shares': position['shares'],
                    'value': sell_value,
                    'return_pct': signal.return_pct,
                    'exit_reason': signal.exit_reason
                })
                
                del self.positions[stock_id]
    
    def calculate_portfolio_value(self, date: str) -> float:
        """
        計算投資組合總價值
        
        Args:
            date: 當前日期
        
        Returns:
            總價值
        """
        portfolio_value = self.capital
        
        for stock_id, position in self.positions.items():
            current_price = self.get_price(stock_id, date)
            if current_price:
                portfolio_value += position['shares'] * current_price
        
        return portfolio_value
    
    def run(
        self,
        start_date: str,
        end_date: str,
        strategy_version: str = 'v2.1'
    ) -> Dict:
        """
        執行回測
        
        Args:
            start_date: 開始日期
            end_date: 結束日期
            strategy_version: 策略版本 ('v2.0' / 'v2.1')
        
        Returns:
            回測結果
        """
        print(f"\n{'='*80}")
        print(f"{'回測 ' + strategy_version + ' 策略':^80}")
        print(f"{'='*80}")
        print(f"期間: {start_date} ~ {end_date}")
        print(f"初始資金: ${self.initial_capital:,.0f}")
        print(f"再平衡頻率: {self.rebalance_frequency}")
        print(f"{'='*80}\n")
        
        # 重置狀態
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.daily_portfolio_values = []
        
        # 獲取再平衡日期
        rebalance_dates = self.get_rebalance_dates(start_date, end_date)
        print(f"再平衡日期數: {len(rebalance_dates)}")
        
        # 獲取所有交易日
        all_trading_days = list(self.db['stock_price'].distinct(
            'date',
            {'date': {'$gte': start_date, '$lte': end_date}}
        ))
        all_trading_days.sort()
        
        print(f"交易日數: {len(all_trading_days)}\n")
        
        # 執行回測
        for date in tqdm(all_trading_days, desc="回測進度"):
            # 再平衡日
            if date in rebalance_dates:
                print(f"\n再平衡日: {date}")
                
                # 選股
                if strategy_version == 'v2.1':
                    selections = self.strategy_v21.select_stocks(date)
                else:  # v2.0
                    selections_v20 = self.strategy_v20.select_stocks(date, top_n=10)
                    # 轉換格式
                    from strategy.integrated_strategy_v21 import StockRanking
                    selections = []
                    for s in selections_v20:
                        ranking = StockRanking(
                            stock_id=s['stock_id'],
                            date=date,
                            factor_score=s['composite_score'],
                            factor_rank=0,
                            pattern_score=0,
                            patterns_detected=[],
                            chip_score=0,
                            chip_signal='unknown',
                            integrated_score=s['composite_score'],
                            position_weight=1.0 / 10  # 等權重
                        )
                        selections.append(ranking)
                
                # 再平衡
                self.rebalance(date, selections)
            
            # 每日檢查出場訊號（僅 v2.1）
            if strategy_version == 'v2.1':
                self.check_daily_exits(date)
            
            # 記錄每日投資組合價值
            portfolio_value = self.calculate_portfolio_value(date)
            self.daily_portfolio_values.append({
                'date': date,
                'value': portfolio_value,
                'return': (portfolio_value - self.initial_capital) / self.initial_capital
            })
        
        # 計算績效指標
        metrics = self.calculate_performance_metrics()
        
        return {
            'metrics': metrics,
            'trades': self.trades,
            'daily_values': self.daily_portfolio_values
        }
    
    def calculate_performance_metrics(self) -> Dict:
        """計算績效指標"""
        df = pd.DataFrame(self.daily_portfolio_values)
        df['daily_return'] = df['value'].pct_change()
        
        # 計算指標
        total_days = len(df)
        years = total_days / 252
        
        final_value = df['value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital
        annual_return = (1 + total_return) ** (1 / years) - 1
        
        # 夏普比率
        sharpe_ratio = df['daily_return'].mean() / df['daily_return'].std() * np.sqrt(252) if df['daily_return'].std() > 0 else 0
        
        # 最大回撤
        cumulative = (1 + df['daily_return']).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # 交易統計
        trades_df = pd.DataFrame([t for t in self.trades if t['action'] == 'sell'])
        
        if len(trades_df) > 0:
            win_rate = (trades_df['return_pct'] > 0).sum() / len(trades_df)
            avg_win = trades_df[trades_df['return_pct'] > 0]['return_pct'].mean() if (trades_df['return_pct'] > 0).sum() > 0 else 0
            avg_loss = trades_df[trades_df['return_pct'] < 0]['return_pct'].mean() if (trades_df['return_pct'] < 0).sum() > 0 else 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
        
        metrics = {
            'trading_days': total_days,
            'years': years,
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades),
            'completed_trades': len(trades_df),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }
        
        return metrics


def print_performance_report(results_v20: Dict, results_v21: Dict):
    """列印績效對比報告"""
    print(f"\n{'='*80}")
    print(f"{'績效對比報告':^80}")
    print(f"{'='*80}\n")
    
    m20 = results_v20['metrics']
    m21 = results_v21['metrics']
    
    # 安全除法函数，处理除零情况
    def safe_pct_change(new_val, old_val):
        if old_val == 0:
            return 0.0 if new_val == 0 else float('inf')
        return (new_val - old_val) / old_val
    
    print(f"{'指標':<25} {'v2.0':>15} {'v2.1':>15} {'改善':>15}")
    print(f"{'-'*80}")
    
    # 報酬指標
    pct_total = safe_pct_change(m21['total_return'], m20['total_return'])
    print(f"{'總報酬':<25} {m20['total_return']:>14.2%} {m21['total_return']:>14.2%} "
          f"{pct_total:>14.2%}" if pct_total != float('inf') else f"{'N/A':>15}")
    
    pct_annual = safe_pct_change(m21['annual_return'], m20['annual_return'])
    print(f"{'年化報酬':<25} {m20['annual_return']:>14.2%} {m21['annual_return']:>14.2%} "
          f"{pct_annual:>14.2%}" if pct_annual != float('inf') else f"{'N/A':>15}")
    
    # 風險指標
    pct_sharpe = safe_pct_change(m21['sharpe_ratio'], m20['sharpe_ratio'])
    print(f"{'夏普比率':<25} {m20['sharpe_ratio']:>15.3f} {m21['sharpe_ratio']:>15.3f} "
          f"{pct_sharpe:>14.2%}" if pct_sharpe != float('inf') else f"{'N/A':>15}")
    
    pct_dd = safe_pct_change(m21['max_drawdown'], abs(m20['max_drawdown']))
    print(f"{'最大回撤':<25} {m20['max_drawdown']:>14.2%} {m21['max_drawdown']:>14.2%} "
          f"{pct_dd:>14.2%}" if pct_dd != float('inf') else f"{'N/A':>15}")
    
    # 交易指標
    pct_wr = safe_pct_change(m21['win_rate'], m20['win_rate'])
    print(f"{'勝率':<25} {m20['win_rate']:>14.2%} {m21['win_rate']:>14.2%} "
          f"{pct_wr:>14.2%}" if pct_wr != float('inf') else f"{'N/A':>15}")
    
    pct_avg_win = safe_pct_change(m21['avg_win'], m20['avg_win'])
    print(f"{'平均獲利':<25} {m20['avg_win']:>14.2%} {m21['avg_win']:>14.2%} "
          f"{pct_avg_win:>14.2%}" if pct_avg_win != float('inf') else f"{'N/A':>15}")
    
    pct_avg_loss = safe_pct_change(m21['avg_loss'], abs(m20['avg_loss']))
    print(f"{'平均虧損':<25} {m20['avg_loss']:>14.2%} {m21['avg_loss']:>14.2%} "
          f"{pct_avg_loss:>14.2%}" if pct_avg_loss != float('inf') else f"{'N/A':>15}")
    
    print(f"{'總交易次數':<25} {m20['total_trades']:>15} {m21['total_trades']:>15} "
          f"{m21['total_trades'] - m20['total_trades']:>15}")
    
    print(f"\n{'='*80}\n")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='v2.1 整合策略回測')
    parser.add_argument('--start-date', type=str, default='2022-01-01', help='開始日期')
    parser.add_argument('--end-date', type=str, default='2024-12-31', help='結束日期')
    parser.add_argument('--initial-capital', type=float, default=10_000_000, help='初始資金')
    parser.add_argument('--rebalance-frequency', type=str, default='monthly', help='再平衡頻率')
    parser.add_argument('--output', type=str, default='backtest_v21_results.json', help='輸出檔案')
    
    args = parser.parse_args()
    
    # 連接資料庫
    print("連接 MongoDB...")
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 回測 v2.0
    print("\n執行 v2.0 回測...")
    backtester_v20 = BacktestV21(
        db,
        initial_capital=args.initial_capital,
        rebalance_frequency=args.rebalance_frequency
    )
    results_v20 = backtester_v20.run(args.start_date, args.end_date, strategy_version='v2.0')
    
    # 回測 v2.1
    print("\n執行 v2.1 回測...")
    backtester_v21 = BacktestV21(
        db,
        initial_capital=args.initial_capital,
        rebalance_frequency=args.rebalance_frequency
    )
    results_v21 = backtester_v21.run(args.start_date, args.end_date, strategy_version='v2.1')
    
    # 列印報告
    print_performance_report(results_v20, results_v21)
    
    # 儲存結果
    output_data = {
        'backtest_config': {
            'start_date': args.start_date,
            'end_date': args.end_date,
            'initial_capital': args.initial_capital,
            'rebalance_frequency': args.rebalance_frequency
        },
        'v2.0': results_v20,
        'v2.1': results_v21
    }
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"✓ 回測結果已儲存: {args.output}")


if __name__ == "__main__":
    main()
