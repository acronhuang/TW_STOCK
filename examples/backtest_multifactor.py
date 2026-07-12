#!/usr/bin/env python3
"""
多因子策略回測

基於信號文件進行回測,計算績效指標
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pymongo import MongoClient
from typing import Dict, List
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class MultiFactorBacktest:
    """多因子策略回測"""
    
    def __init__(self,
                 initial_cash: float = 1_000_000,
                 commission_rate: float = 0.001425,  # 0.1425% 證交稅
                 slippage_rate: float = 0.003,  # 0.3% 滑價
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        """
        初始化回測
        
        Args:
            initial_cash: 初始資金
            commission_rate: 手續費率（含證交稅）
            slippage_rate: 滑價率
            mongo_uri: MongoDB URI
            db_name: 資料庫名稱
        """
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        
        # MongoDB
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        
        # 回測狀態
        self.cash = initial_cash
        self.positions = {}  # {symbol: {'shares': int, 'cost_basis': float}}
        self.equity_history = []
        self.trade_history = []
        
    def _to_float(self, value):
        """轉換 Decimal128 為 float"""
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        return float(value) if value is not None else 0.0
    
    def get_price(self, symbol: str, date: datetime, price_type: str = 'close') -> float:
        """
        獲取股票價格
        
        Args:
            symbol: 股票代碼
            date: 日期
            price_type: 價格類型 ('open', 'close', 'adj_close')
        
        Returns:
            股票價格
        """
        doc = self.db.stock_price.find_one(
            {'symbol': symbol, 'date': date},
            {price_type: 1, 'adj_close': 1}
        )
        
        if not doc:
            # 嘗試找最近的交易日
            doc = self.db.stock_price.find_one(
                {'symbol': symbol, 'date': {'$lte': date}},
                {price_type: 1, 'adj_close': 1},
                sort=[('date', -1)]
            )
        
        if not doc:
            return None
        
        # 優先使用 adj_close（考慮除權息）
        if price_type == 'close' and 'adj_close' in doc and doc['adj_close'] is not None:
            return self._to_float(doc['adj_close'])
        
        return self._to_float(doc.get(price_type, 0))
    
    def calculate_portfolio_value(self, date: datetime) -> float:
        """
        計算投資組合總價值
        
        Args:
            date: 日期
        
        Returns:
            總價值（現金 + 持股市值）
        """
        market_value = 0
        
        for symbol, position in self.positions.items():
            price = self.get_price(symbol, date)
            if price:
                market_value += position['shares'] * price
        
        return self.cash + market_value
    
    def rebalance(self, date: datetime, signals: pd.DataFrame):
        """
        調倉
        
        Args:
            date: 調倉日期
            signals: 信號 DataFrame（包含 symbol, weight）
        """
        # 計算目標持股
        total_value = self.calculate_portfolio_value(date)
        target_positions = {}
        
        for _, row in signals.iterrows():
            symbol = row['symbol']
            weight = row['weight']
            target_value = total_value * weight
            
            price = self.get_price(symbol, date, price_type='close')
            if not price or price <= 0:
                continue
            
            # 計算目標股數（買進以漲停價計算，實際執行較保守）
            price_with_slippage = price * (1 + self.slippage_rate)
            target_shares = int(target_value / price_with_slippage / 1000) * 1000  # 整張
            
            if target_shares > 0:
                target_positions[symbol] = {
                    'shares': target_shares,
                    'price': price
                }
        
        # 賣出不在目標清單的持股
        for symbol in list(self.positions.keys()):
            if symbol not in target_positions:
                self._sell(symbol, date, self.positions[symbol]['shares'])
        
        # 買入或調整持股
        for symbol, target in target_positions.items():
            current_shares = self.positions.get(symbol, {}).get('shares', 0)
            diff = target['shares'] - current_shares
            
            if diff > 0:
                # 買入
                self._buy(symbol, date, diff, target['price'])
            elif diff < 0:
                # 賣出
                self._sell(symbol, date, abs(diff))
    
    def _buy(self, symbol: str, date: datetime, shares: int, price: float):
        """買入股票"""
        if shares <= 0:
            return
        
        # 考慮滑價
        actual_price = price * (1 + self.slippage_rate)
        cost = shares * actual_price
        commission = cost * self.commission_rate
        total_cost = cost + commission
        
        if total_cost > self.cash:
            # 資金不足，按可用資金買入
            shares = int((self.cash / (actual_price * (1 + self.commission_rate))) / 1000) * 1000
            if shares <= 0:
                return
            cost = shares * actual_price
            commission = cost * self.commission_rate
            total_cost = cost + commission
        
        # 更新現金
        self.cash -= total_cost
        
        # 更新持倉
        if symbol in self.positions:
            # 已有持倉，更新成本均價
            old_shares = self.positions[symbol]['shares']
            old_cost = self.positions[symbol]['cost_basis'] * old_shares
            new_shares = old_shares + shares
            new_cost = old_cost + cost
            self.positions[symbol] = {
                'shares': new_shares,
                'cost_basis': new_cost / new_shares
            }
        else:
            self.positions[symbol] = {
                'shares': shares,
                'cost_basis': actual_price
            }
        
        # 記錄交易
        self.trade_history.append({
            'date': date,
            'symbol': symbol,
            'action': 'BUY',
            'shares': shares,
            'price': actual_price,
            'cost': cost,
            'commission': commission,
            'total': total_cost
        })
    
    def _sell(self, symbol: str, date: datetime, shares: int):
        """賣出股票"""
        if symbol not in self.positions or shares <= 0:
            return
        
        position = self.positions[symbol]
        shares = min(shares, position['shares'])  # 不能賣超過持有數量
        
        price = self.get_price(symbol, date, price_type='close')
        if not price:
            return
        
        # 考慮滑價（賣出以跌停價計算）
        actual_price = price * (1 - self.slippage_rate)
        proceeds = shares * actual_price
        commission = proceeds * self.commission_rate
        total_proceeds = proceeds - commission
        
        # 更新現金
        self.cash += total_proceeds
        
        # 更新持倉
        position['shares'] -= shares
        if position['shares'] <= 0:
            del self.positions[symbol]
        
        # 計算盈虧
        pnl = (actual_price - position['cost_basis']) * shares - commission
        
        # 記錄交易
        self.trade_history.append({
            'date': date,
            'symbol': symbol,
            'action': 'SELL',
            'shares': shares,
            'price': actual_price,
            'proceeds': proceeds,
            'commission': commission,
            'total': total_proceeds,
            'pnl': pnl
        })
    
    def run(self, signals_df: pd.DataFrame) -> Dict:
        """
        執行回測
        
        Args:
            signals_df: 信號 DataFrame（包含 date, symbol, action, weight）
        
        Returns:
            回測結果字典
        """
        print("\n" + "=" * 80)
        print("多因子策略回測")
        print("=" * 80)
        print(f"初始資金: ${self.initial_cash:,.0f}")
        print(f"手續費率: {self.commission_rate:.4%}")
        print(f"滑價率: {self.slippage_rate:.2%}")
        print("-" * 80)
        
        # 重置狀態
        self.cash = self.initial_cash
        self.positions = {}
        self.equity_history = []
        self.trade_history = []
        
        # 按日期分組信號
        signals_by_date = signals_df.groupby('date')
        dates = sorted(signals_df['date'].unique())
        
        # 獲取所有交易日
        start_date = dates[0]
        end_date = dates[-1]
        
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        trading_dates = []
        
        for date in all_dates:
            if self.db.stock_price.count_documents({'date': date.to_pydatetime()}, limit=1) > 0:
                trading_dates.append(date.to_pydatetime())
        
        print(f"回測期間: {start_date.date()} ~ {end_date.date()}")
        print(f"交易日數: {len(trading_dates)}")
        print(f"調倉次數: {len(dates)}")
        print("-" * 80)
        
        # 執行回測
        for i, date in enumerate(trading_dates, 1):
            # 檢查是否需要調倉
            if date in dates:
                signals = signals_by_date.get_group(date)
                print(f"[{date.date()}] 調倉 - 目標持股 {len(signals)} 支")
                self.rebalance(date, signals)
            
            # 記錄權益
            equity = self.calculate_portfolio_value(date)
            self.equity_history.append({
                'date': date,
                'equity': equity,
                'cash': self.cash,
                'market_value': equity - self.cash
            })
            
            # 定期輸出進度
            if i % 50 == 0:
                print(f"  [{i}/{len(trading_dates)}] {date.date()} | 總權益: ${equity:,.0f}")
        
        print("-" * 80)
        print(f"✅ 回測完成！執行 {len(self.trade_history)} 筆交易")
        
        # 計算績效指標
        metrics = self._calculate_metrics()
        
        return {
            'metrics': metrics,
            'equity_history': pd.DataFrame(self.equity_history),
            'trade_history': pd.DataFrame(self.trade_history),
            'final_positions': self.positions
        }
    
    def _calculate_metrics(self) -> pd.Series:
        """計算績效指標"""
        equity_df = pd.DataFrame(self.equity_history)
        trades_df = pd.DataFrame(self.trade_history)
        
        # 基本指標
        initial_value = self.initial_cash
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
        
        # 夏普比率（假設無風險利率為 0）
        sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
        
        # 最大回撤
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax']
        max_drawdown = equity_df['drawdown'].min() * 100
        
        # 波動率
        volatility = daily_returns.std() * np.sqrt(252) * 100
        
        # 交易統計
        total_trades = len(trades_df)
        
        if total_trades > 0:
            # 勝率（以賣出交易計算）
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            if len(sell_trades) > 0:
                winning_trades = len(sell_trades[sell_trades['pnl'] > 0])
                win_rate = winning_trades / len(sell_trades) * 100
                
                # 盈虧比
                avg_win = sell_trades[sell_trades['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
                avg_loss = abs(sell_trades[sell_trades['pnl'] < 0]['pnl'].mean()) if len(sell_trades) > winning_trades else 0
                profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
            else:
                win_rate = 0
                profit_factor = 0
        else:
            win_rate = 0
            profit_factor = 0
        
        return pd.Series({
            '初始資金': f'${initial_value:,.0f}',
            '最終權益': f'${final_value:,.0f}',
            '總報酬率': f'{total_return:.2f}%',
            '年化報酬率': f'{annual_return:.2f}%',
            '夏普比率': f'{sharpe_ratio:.3f}',
            '最大回撤': f'{max_drawdown:.2f}%',
            '波動率': f'{volatility:.2f}%',
            '交易次數': total_trades,
            '勝率': f'{win_rate:.2f}%' if total_trades > 0 else 'N/A',
            '盈虧比': f'{profit_factor:.2f}' if total_trades > 0 else 'N/A',
            '回測天數': days,
            '年數': f'{years:.2f}'
        })


def main():
    """主函數"""
    # 載入信號
    signals_file = Path(__file__).parent.parent / 'data' / 'multifactor_signals.csv'
    
    if not signals_file.exists():
        print(f"❌ 找不到信號文件: {signals_file}")
        print("請先運行 multifactor_strategy.py 生成交易信號")
        return
    
    signals_df = pd.read_csv(signals_file)
    signals_df['date'] = pd.to_datetime(signals_df['date'])
    # 確保 symbol 是字符串類型
    signals_df['symbol'] = signals_df['symbol'].astype(str)
    
    # 執行回測
    backtest = MultiFactorBacktest(
        initial_cash=1_000_000,
        commission_rate=0.001425,  # 0.1425% 證交稅
        slippage_rate=0.003  # 0.3% 滑價
    )
    
    results = backtest.run(signals_df)
    
    # 顯示績效指標
    print("\n" + "=" * 80)
    print("績效指標")
    print("=" * 80)
    print(results['metrics'].to_string())
    
    # 保存結果
    output_dir = Path(__file__).parent.parent / 'charts'
    output_dir.mkdir(exist_ok=True)
    
    # 權益曲線
    equity_file = output_dir / 'multifactor_equity.csv'
    results['equity_history'].to_csv(equity_file, index=False, encoding='utf-8-sig')
    print(f"\n💾 權益曲線已保存: {equity_file}")
    
    # 交易記錄
    trades_file = output_dir / 'multifactor_trades.csv'
    results['trade_history'].to_csv(trades_file, index=False, encoding='utf-8-sig')
    print(f"💾 交易記錄已保存: {trades_file}")
    
    # 顯示交易摘要
    trades_df = results['trade_history']
    if len(trades_df) > 0:
        print("\n" + "=" * 80)
        print(f"交易記錄（共 {len(trades_df)} 筆，顯示前 10 筆）")
        print("=" * 80)
        print(trades_df.head(10)[['date', 'symbol', 'action', 'shares', 'price', 'total']].to_string(index=False))
    
    print("\n" + "=" * 80)
    print("✅ 回測完成！")
    print("💡 結果已保存到 charts/ 目錄")
    print("💡 可在 Dashboard (http://localhost:8502) 的「策略比較」頁面查看視覺化結果")
    print("=" * 80)


if __name__ == '__main__':
    main()
