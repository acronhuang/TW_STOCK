#!/usr/bin/env python3
"""
形態回測腳本 (Pattern Backtest Script)

回測形態偵測策略的歷史表現。

功能：
1. 單一形態回測
2. 形態組合回測
3. 與基準策略對比
4. 生成詳細回測報告

作者: Ming
創建日期: 2026-02-23
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

from src.morphology import PatternDetector


class PatternBacktester:
    """形態回測器"""
    
    def __init__(self, initial_capital=1_000_000, commission_rate=0.001425):
        """
        初始化回測器
        
        Args:
            initial_capital: 初始資金
            commission_rate: 手續費率（0.1425%）
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.detector = PatternDetector()
        
        # 連接 MongoDB
        try:
            self.client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
            self.db = self.client['tw_stock_analysis']
            self.client.server_info()
            print("✓ MongoDB 連接成功")
        except Exception as e:
            print(f"✗ MongoDB 連接失敗: {e}")
            raise
    
    def get_stock_data(self, stock_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        """獲取股票數據"""
        data = list(self.db.stock_price.find(
            {
                'stock_id': stock_id,
                'date': {'$gte': start_date, '$lte': end_date}
            },
            {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
        ).sort('date', 1))
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        return df
    
    def backtest_single_pattern(
        self,
        pattern_name: str,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        holding_days: int = 20,
        stop_loss: float = -0.08
    ) -> Dict:
        """
        回測單一形態策略
        
        Args:
            pattern_name: 形態名稱
            stock_list: 股票列表
            start_date: 開始日期
            end_date: 結束日期
            holding_days: 持有天數
            stop_loss: 停損比例
        
        Returns:
            回測結果字典
        """
        print(f"\n回測形態: {pattern_name}")
        print(f"股票數量: {len(stock_list)}")
        print(f"期間: {start_date} ~ {end_date}")
        print(f"持有天數: {holding_days}")
        print(f"停損: {stop_loss:.1%}")
        print("-" * 70)
        
        trades = []
        
        for stock_id in stock_list:
            # 獲取數據
            df = self.get_stock_data(stock_id, start_date, end_date)
            
            if df is None or len(df) < 120:
                continue
            
            # 偵測形態
            try:
                results = self.detector.detect_all(df, stock_id=stock_id)
                pattern_result = results.get(pattern_name, {})
                
                if not pattern_result.get('detected'):
                    continue
                
                details = pattern_result['details']
                
                # 遍歷所有形態出現日期
                for pattern_date in details.index:
                    # 找到該日期的位置
                    try:
                        idx = df.index.get_loc(pattern_date)
                    except KeyError:
                        continue
                    
                    # 次日進場（開盤價）
                    if idx + 1 >= len(df):
                        continue
                    
                    entry_date = df.index[idx + 1]
                    entry_price = df['open'].iloc[idx + 1]
                    
                    # 持有期間
                    exit_idx = min(idx + 1 + holding_days, len(df) - 1)
                    
                    # 檢查停損
                    exit_date = df.index[exit_idx]
                    exit_price = df['close'].iloc[exit_idx]
                    exit_reason = 'time_exit'
                    
                    # 逐日檢查停損
                    for i in range(idx + 1, exit_idx + 1):
                        current_price = df['close'].iloc[i]
                        pnl = (current_price - entry_price) / entry_price
                        
                        if pnl <= stop_loss:
                            exit_date = df.index[i]
                            exit_price = current_price
                            exit_reason = 'stop_loss'
                            break
                    
                    # 計算報酬
                    gross_return = (exit_price - entry_price) / entry_price
                    commission = (entry_price + exit_price) * self.commission_rate
                    net_return = gross_return - commission / entry_price
                    
                    # 記錄交易
                    trade = {
                        'stock_id': stock_id,
                        'entry_date': entry_date.strftime('%Y-%m-%d'),
                        'entry_price': entry_price,
                        'exit_date': exit_date.strftime('%Y-%m-%d'),
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'holding_days': (exit_date - entry_date).days,
                        'gross_return': gross_return,
                        'net_return': net_return,
                        'pattern_score': details.loc[pattern_date].get('pattern_score', 0)
                    }
                    
                    trades.append(trade)
            
            except Exception as e:
                print(f"⚠️  處理 {stock_id} 時發生錯誤: {e}")
                continue
        
        # 計算績效指標
        if not trades:
            print("⚠️ 無交易記錄")
            return None
        
        df_trades = pd.DataFrame(trades)
        
        # 基本統計
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['net_return'] > 0)
        win_rate = winning_trades / total_trades
        
        avg_return = df_trades['net_return'].mean()
        total_return = (1 + df_trades['net_return']).prod() - 1
        
        max_win = df_trades['net_return'].max()
        max_loss = df_trades['net_return'].min()
        
        # 夏普比率（簡化版）
        sharpe = avg_return / df_trades['net_return'].std() if df_trades['net_return'].std() > 0 else 0
        
        # 最大回撤
        cum_returns = (1 + df_trades['net_return']).cumprod()
        max_drawdown = (cum_returns / cum_returns.cummax() - 1).min()
        
        result = {
            'pattern_name': pattern_name,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'total_return': total_return,
            'max_win': max_win,
            'max_loss': max_loss,
            'sharpe': sharpe,
            'max_drawdown': max_drawdown,
            'trades': trades
        }
        
        # 顯示結果
        print(f"\n回測結果:")
        print(f"  總交易數: {total_trades}")
        print(f"  獲利交易: {winning_trades} ({win_rate:.1%})")
        print(f"  平均報酬: {avg_return:+.2%}")
        print(f"  總報酬: {total_return:+.2%}")
        print(f"  最大獲利: {max_win:+.2%}")
        print(f"  最大虧損: {max_loss:+.2%}")
        print(f"  夏普比率: {sharpe:.3f}")
        print(f"  最大回撤: {max_drawdown:.2%}")
        
        return result
    
    def backtest_all_patterns(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        holding_days: int = 20
    ) -> Dict:
        """回測所有形態"""
        print("\n" + "=" * 70)
        print("回測所有形態")
        print("=" * 70)
        
        patterns = [
            'bottom_reversal',
            'w_bottom',
            'neckline_breakout',
            'volume_surge'
        ]
        
        results = {}
        
        for pattern in patterns:
            result = self.backtest_single_pattern(
                pattern,
                stock_list,
                start_date,
                end_date,
                holding_days
            )
            
            if result:
                results[pattern] = result
        
        # 比較結果
        print("\n" + "=" * 70)
        print("形態績效比較")
        print("=" * 70)
        print(f"{'形態':25s} | {'交易數':>7s} | {'勝率':>8s} | {'平均報酬':>10s} | {'夏普':>7s}")
        print("-" * 70)
        
        for pattern, result in results.items():
            print(f"{pattern:25s} | "
                  f"{result['total_trades']:7d} | "
                  f"{result['win_rate']:7.1%} | "
                  f"{result['avg_return']:+9.2%} | "
                  f"{result['sharpe']:7.3f}")
        
        print("=" * 70)
        
        return results
    
    def backtest_combined_strategy(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str,
        min_patterns: int = 1,
        min_score: float = 0.6,
        holding_days: int = 20
    ) -> Dict:
        """
        回測組合策略（多形態確認）
        
        Args:
            stock_list: 股票列表
            start_date: 開始日期
            end_date: 結束日期
            min_patterns: 最少需要的形態數量
            min_score: 最低綜合評分
            holding_days: 持有天數
        """
        print("\n" + "=" * 70)
        print(f"回測組合策略（至少 {min_patterns} 個形態，評分 > {min_score}）")
        print("=" * 70)
        
        # 按月調倉
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        rebalance_dates = pd.date_range(start, end, freq='M')
        
        trades = []
        portfolio_values = [self.initial_capital]
        portfolio_dates = [start]
        
        for rebal_date in rebalance_dates:
            print(f"\n調倉日期: {rebal_date.strftime('%Y-%m-%d')}")
            
            # 讀取所有股票近 120 天數據
            stocks_data = {}
            lookback_start = (rebal_date - timedelta(days=120)).strftime('%Y-%m-%d')
            rebal_str = rebal_date.strftime('%Y-%m-%d')
            
            for stock_id in stock_list:
                df = self.get_stock_data(stock_id, lookback_start, rebal_str)
                
                if df is not None and len(df) >= 60:
                    stocks_data[stock_id] = df
            
            if not stocks_data:
                continue
            
            # 形態過濾
            filtered = self.detector.filter_stocks(
                stocks_data,
                min_patterns=min_patterns,
                min_score=min_score,
                lookback_days=5
            )
            
            if not filtered:
                print("  ✗ 無符合條件的股票")
                continue
            
            # 選出前 10 支
            selected = filtered[:10]
            print(f"  ✓ 選出 {len(selected)} 支股票")
            
            # 等權重配置
            weight = 1.0 / len(selected)
            
            # 進場
            for stock_id, score, patterns in selected:
                # 次日開盤進場
                next_date = rebal_date + timedelta(days=1)
                
                # 獲取進場價格
                entry_data = self.get_stock_data(
                    stock_id,
                    next_date.strftime('%Y-%m-%d'),
                    (next_date + timedelta(days=5)).strftime('%Y-%m-%d')
                )
                
                if entry_data is None or entry_data.empty:
                    continue
                
                entry_price = entry_data['open'].iloc[0]
                entry_date = entry_data.index[0]
                
                # 出場日期
                exit_date = entry_date + timedelta(days=holding_days)
                
                exit_data = self.get_stock_data(
                    stock_id,
                    exit_date.strftime('%Y-%m-%d'),
                    (exit_date + timedelta(days=5)).strftime('%Y-%m-%d')
                )
                
                if exit_data is None or exit_data.empty:
                    continue
                
                exit_price = exit_data['close'].iloc[0]
                actual_exit_date = exit_data.index[0]
                
                # 計算報酬
                gross_return = (exit_price - entry_price) / entry_price
                net_return = gross_return - (entry_price + exit_price) * self.commission_rate / entry_price
                
                trade = {
                    'rebalance_date': rebal_date.strftime('%Y-%m-%d'),
                    'stock_id': stock_id,
                    'entry_date': entry_date.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_date': actual_exit_date.strftime('%Y-%m-%d'),
                    'exit_price': exit_price,
                    'weight': weight,
                    'net_return': net_return,
                    'pattern_score': score,
                    'patterns': list(patterns.keys())
                }
                
                trades.append(trade)
        
        if not trades:
            print("⚠️ 無交易記錄")
            return None
        
        # 計算績效
        df_trades = pd.DataFrame(trades)
        
        # 按調倉期計算
        grouped = df_trades.groupby('rebalance_date')
        
        period_returns = []
        for rebal_date, group in grouped:
            # 該期的加權報酬
            period_return = (group['net_return'] * group['weight']).sum()
            period_returns.append(period_return)
        
        # 績效指標
        total_return = (1 + pd.Series(period_returns)).prod() - 1
        avg_return = pd.Series(period_returns).mean()
        sharpe = avg_return / pd.Series(period_returns).std() if pd.Series(period_returns).std() > 0 else 0
        
        cum_returns = (1 + pd.Series(period_returns)).cumprod()
        max_drawdown = (cum_returns / cum_returns.cummax() - 1).min()
        
        win_rate = sum(1 for r in period_returns if r > 0) / len(period_returns)
        
        result = {
            'strategy': 'combined',
            'total_trades': len(trades),
            'periods': len(period_returns),
            'win_rate': win_rate,
            'avg_return': avg_return,
            'total_return': total_return,
            'sharpe': sharpe,
            'max_drawdown': max_drawdown,
            'period_returns': period_returns,
            'trades': trades
        }
        
        # 顯示結果
        print("\n" + "=" * 70)
        print("組合策略回測結果")
        print("=" * 70)
        print(f"  總交易數: {len(trades)}")
        print(f"  調倉次數: {len(period_returns)}")
        print(f"  勝率: {win_rate:.1%}")
        print(f"  平均報酬: {avg_return:+.2%}")
        print(f"  總報酬: {total_return:+.2%}")
        print(f"  夏普比率: {sharpe:.3f}")
        print(f"  最大回撤: {max_drawdown:.2%}")
        print("=" * 70)
        
        return result
    
    def compare_with_baseline(
        self,
        stock_list: List[str],
        start_date: str,
        end_date: str
    ):
        """與基準策略對比（等權重 vs 形態過濾）"""
        print("\n" + "=" * 70)
        print("基準對比：等權重 vs 形態過濾")
        print("=" * 70)
        
        # 策略 A: 等權重（無過濾）
        print("\n策略 A: 等權重（前 10 支）")
        # ... 實作等權重回測
        
        # 策略 B: 形態過濾
        print("\n策略 B: 形態過濾（min_patterns=1, min_score=0.6）")
        result_b = self.backtest_combined_strategy(
            stock_list,
            start_date,
            end_date,
            min_patterns=1,
            min_score=0.6
        )
        
        # 對比
        # ... 顯示對比結果
        
        return result_b
    
    def generate_report(self, results: Dict, output_file: str = None):
        """生成回測報告"""
        report = {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'results': results
        }
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"\n✓ 報告已儲存: {output_file}")
        
        return report


def main():
    """主函數"""
    print("\n" + "=" * 70)
    print("形態回測腳本 (Pattern Backtest Script)")
    print("=" * 70)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # 初始化回測器
    backtester = PatternBacktester(initial_capital=1_000_000)
    
    # 測試股票列表
    stock_list = [
        '2330', '2317', '2454', '2308', '2382',
        '6505', '2881', '2891', '2886', '2303'
    ]
    
    # 回測期間
    start_date = '2023-01-01'
    end_date = '2024-06-30'
    
    # 執行回測
    
    # 1. 單一形態回測
    print("\n1️⃣ 單一形態回測")
    result_bottom = backtester.backtest_single_pattern(
        'bottom_reversal',
        stock_list,
        start_date,
        end_date,
        holding_days=20
    )
    
    # 2. 所有形態回測
    print("\n2️⃣ 所有形態回測")
    results_all = backtester.backtest_all_patterns(
        stock_list,
        start_date,
        end_date,
        holding_days=20
    )
    
    # 3. 組合策略回測
    print("\n3️⃣ 組合策略回測")
    result_combined = backtester.backtest_combined_strategy(
        stock_list,
        start_date,
        end_date,
        min_patterns=1,
        min_score=0.6,
        holding_days=20
    )
    
    # 4. 生成報告
    print("\n4️⃣ 生成報告")
    report = backtester.generate_report(
        {
            'single_pattern': result_bottom,
            'all_patterns': results_all,
            'combined': result_combined
        },
        output_file='backtest_report.json'
    )
    
    print("\n✓ 回測完成！")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
