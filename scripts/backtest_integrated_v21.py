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


def _q(date) -> datetime:
    """日期（字串或 datetime）→ UTC 午夜 datetime，供 MongoDB 查詢使用。

    2026-07-19 修：本檔原本把 'YYYY-MM-DD' 字串直接丟進 Mongo 查 stock_price.date，
    但該欄位是 Date 型別 → 查詢恆回 0 筆，交易日數為 0，
    最終在 calculate_performance_metrics 以 KeyError: 'value' 崩潰。
    也就是說這支回測從未成功執行過。

    修法刻意最小化：**只在查詢邊界轉型**，內部一律維持字串表示，
    因此 `date in rebalance_dates`、`get_price(sid, date)`、交易紀錄等呼叫端全不受影響。
    """
    ts = pd.to_datetime(date)
    return datetime(ts.year, ts.month, ts.day)


class BacktestV21:
    """v2.1 策略回測器"""
    
    def __init__(
        self,
        db_connection,
        initial_capital: float = 10_000_000,
        rebalance_frequency: str = 'monthly',
        fee_rate: float = 0.001425,
        fee_discount: float = 0.6,
        tax_rate: float = 0.003,
        min_fee: float = 20.0,
        quality_source: str = 'fundamental',   # none / fundamental / legacy(對齊 production MFS)
        entry_lag: int = 1,
        stale_exit_days: int = 20
    ):
        """
        初始化
        
        Args:
            db_connection: MongoDB 連接
            initial_capital: 初始資金
            rebalance_frequency: 再平衡頻率 ('monthly' / 'quarterly' / 'semiannual')
        """
        self.db = db_connection
        self.initial_capital = initial_capital
        self.rebalance_frequency = rebalance_frequency
        
        # 初始化策略
        self.strategy_v21 = IntegratedStrategyV21(db_connection)
        self.strategy_v20 = MultiFactorStrategy(db_connection)

        for strat in (self.strategy_v21.factor_strategy, self.strategy_v20):
            if quality_source == 'none':
                strat.update_config({'quality': None})     # 移除並自動正規化權重
            else:
                strat.quality_source = quality_source
        if quality_source == 'none':
            print(f"⚠️  已移除 quality 因子,權重重新分配: "
                  f"{ {k: round(v['weight'], 3) for k, v in
                       self.strategy_v20.factor_config.items()} }")
        elif quality_source == 'legacy':
            print("⚠️  quality 使用 stock_factors 常數值 —— 有前視偏誤,僅供對照")
        else:
            print("✓ quality 取自 fundamental_factors(以 available_from 落後)")
        
        # 回測狀態
        # 台股交易成本:手續費 0.1425%(雙邊,常見 6 折,最低 20 元)
        # 證交稅 0.3% —— 僅賣出課徵
        self.fee_rate = fee_rate
        self.fee_discount = fee_discount
        self.tax_rate = tax_rate
        self.min_fee = min_fee
        self.total_fees = 0.0
        self.total_taxes = 0.0

        # --- 偏誤控制 ---
        # quality 因子(roe/roa/profit_margin/debt_ratio)在 stock_factors 是常數,
        # 等於把近期財報回頭貼到歷史每一天 → 純前視偏誤,預設關閉。
        self.quality_source = quality_source
        # 因子以當日收盤算出,不可能在當日收盤成交 → 延後 N 個交易日進場。
        self.entry_lag = entry_lag
        # 連續無報價達此天數視為下市/長期停牌,以最後已知價強制出場。
        self.stale_exit_days = stale_exit_days
        self.last_price = {}      # {stock_id: 最後已知收盤}
        self.stale_days = {}      # {stock_id: 連續無報價天數}
        self.forced_exits = 0

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
        
        # 頻率 → 間隔月數。未知值一律拋錯:先前只實作 monthly,傳其他值會安靜
        # 回傳空清單,整段回測拿 0 個再平衡日還照跑,不會有任何錯誤訊息。
        step_months = {'monthly': 1, 'quarterly': 3, 'semiannual': 6}
        if self.rebalance_frequency not in step_months:
            raise ValueError(
                f"不支援的 rebalance_frequency: {self.rebalance_frequency!r}"
                f"(可用:{'/'.join(step_months)})")
        step = step_months[self.rebalance_frequency]

        # 每期第一個交易日
        while current <= end:
            trading_day = self._find_next_trading_day(current.strftime('%Y-%m-%d'))
            if trading_day:
                dates.append(trading_day)

            m = current.month - 1 + step
            current = current.replace(year=current.year + m // 12, month=m % 12 + 1)

        return dates
    
    def _find_next_trading_day(self, date: str) -> str:
        """找到下一個交易日"""
        current = pd.to_datetime(date)
        
        for i in range(10):  # 最多往後找 10 天
            check_date = (current + timedelta(days=i)).strftime('%Y-%m-%d')
            
            # 檢查是否有交易數據（date 為 Date 型別，須轉型查詢）
            has_data = self.db['stock_price'].find_one({
                'date': _q(check_date)
            })
            
            if has_data:
                return check_date
        
        return None
    
    def get_price(self, stock_id: str, date: str) -> float:
        """獲取股價"""
        data = self.db['stock_price'].find_one({
            'stock_id': stock_id,
            'date': _q(date)
        })

        if not data:
            return None
        # 價格欄位為 Decimal128（見記憶 ssh-access-166），需轉 float 才能參與運算
        # 還原價優先;adj_close 為空代表 close 本身就缺值(全庫 23 筆)
        px = data.get('adj_close')
        if px is None:
            px = data.get('close')
        if px is None:
            return None
        val = float(str(px))
        self.last_price[stock_id] = val      # 供無報價時沿用
        return val
    
    def rebalance(self, date: str, selections: List):
        """
        再平衡持倉
        
        Args:
            date: 再平衡日期
            selections: 選股結果（StockRanking 列表）
        """
        # 2026-07-19 重寫。原實作有兩個獨立的會計錯誤：
        #
        # (1) 資金配置基數在迴圈內縮小：
        #     target_value = self.capital * weight  且迴圈內 self.capital -= buy_value
        #     → 第 n 檔的基數是第 1 檔的 0.9^(n-1)。實測 2023-07-03 十檔買單為
        #       991,200 → 897,600 → 790,350 →…（公比 0.9），約 1/3 資金從未進場。
        #
        # (2) 已持有且仍在名單內的股票，不賣舊部位就直接覆蓋 self.positions[stock_id]
        #     → 股數憑空蒸發。實測 1608 從 42,000 股被覆蓋成 17,000 股，
        #       25,000 股消失而現金照扣。這是漏帳，也是 -71% 報酬的主因。
        #
        # 改為標準的目標權重再平衡：以「總資產」為基數一次算定 → 先賣後買 → 按差額調整。
        # 成本基礎改用加權平均，使加碼後的 return_pct 仍有意義。

        # 0) 配置基數：總資產（現金 + 持股市值），在迴圈外一次算定
        total_value = self.calculate_portfolio_value(date)

        # 1) 算出每檔的目標股數（整張）
        targets = {}
        for selection in selections:
            price = self.get_price(selection.stock_id, date)
            if not price:
                continue
            shares = int(total_value * selection.position_weight / price / 1000) * 1000
            targets[selection.stock_id] = {
                'shares': shares,
                'price': price,
                'weight': selection.position_weight,
            }

        # 2) 先賣：不在名單內的全數出清；仍在名單內但超過目標的減碼
        for stock_id in list(self.positions.keys()):
            price = self.get_price(stock_id, date)
            if not price:
                continue  # 無報價當日不動作，避免以錯誤價格成交
            held = self.positions[stock_id]['shares']
            want = targets[stock_id]['shares'] if stock_id in targets else 0
            if want < held:
                self._execute_sell(stock_id, date, price, held - want)

        # 3) 再買：不足目標的加碼（此時現金已到位）
        for stock_id, t in targets.items():
            held = self.positions.get(stock_id, {}).get('shares', 0)
            qty = t['shares'] - held
            if qty <= 0:
                continue
            # 整張化與價格變動可能造成微幅超支，以現有現金為上限截斷
            cost_mult = 1.0 + self.fee_rate * self.fee_discount
            if qty * t['price'] * cost_mult > self.capital:
                qty = int(self.capital / (t['price'] * cost_mult) / 1000) * 1000
            if qty > 0:
                self._execute_buy(stock_id, date, t['price'], qty, t['weight'])

    def _fee(self, value: float) -> float:
        """手續費:價金 × 費率 × 折扣,不低於最低收費。"""
        return max(self.min_fee, value * self.fee_rate * self.fee_discount)

    def _execute_sell(self, stock_id: str, date: str, price: float, shares: int):
        """賣出指定股數（可為部分減碼）。"""
        position = self.positions[stock_id]
        entry = position['entry_price']
        value = shares * price
        fee = self._fee(value)
        tax = value * self.tax_rate          # 證交稅只在賣出課徵
        self.capital += value - fee - tax
        self.total_fees += fee
        self.total_taxes += tax

        self.trades.append({
            'date': date,
            'stock_id': stock_id,
            'action': 'sell',
            'price': price,
            'shares': shares,
            'value': value,
            'fee': fee,
            'tax': tax,
            'return_pct': (price - entry) / entry if entry else 0.0,
        })

        remaining = position['shares'] - shares
        if remaining > 0:
            position['shares'] = remaining      # 減碼：成本基礎不變
        else:
            del self.positions[stock_id]

    def _execute_buy(self, stock_id: str, date: str, price: float,
                     shares: int, weight: float):
        """買進指定股數（可為加碼），成本基礎以加權平均更新。"""
        value = shares * price
        fee = self._fee(value)
        self.capital -= value + fee
        self.total_fees += fee

        self.trades.append({
            'date': date,
            'stock_id': stock_id,
            'action': 'buy',
            'price': price,
            'shares': shares,
            'value': value,
            'fee': fee,
            'weight': weight,
        })

        pos = self.positions.get(stock_id)
        if pos:
            old_shares = pos['shares']
            total_shares = old_shares + shares
            pos['entry_price'] = (pos['entry_price'] * old_shares + value) / total_shares
            pos['shares'] = total_shares
        else:
            self.positions[stock_id] = {
                'shares': shares,
                'entry_price': price,
                'entry_date': date,
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
    
    def _handle_stale_positions(self, date: str):
        """連續無報價超過門檻者,以最後已知價強制出場並計入交易紀錄。"""
        for stock_id in list(self.positions.keys()):
            if self.get_price(stock_id, date) is not None:
                self.stale_days[stock_id] = 0
                continue
            n = self.stale_days.get(stock_id, 0) + 1
            self.stale_days[stock_id] = n
            if n < self.stale_exit_days:
                continue
            px = self.last_price.get(stock_id)
            if px is None:
                del self.positions[stock_id]     # 從無報價,無法估值
                continue
            self._execute_sell(stock_id, date, px, self.positions[stock_id]['shares'])
            self.forced_exits += 1

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
            if not current_price:
                # 無報價不代表市值為 0 —— 沿用最後已知價,否則會製造假的淨值坑洞,
                # 且下市股的虧損會永遠不入帳(舊版就是這樣把勝率灌高的)。
                current_price = self.last_price.get(stock_id)
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
        # date 為 Date 型別 → 以 datetime 查詢，取回後轉回字串以維持內部表示一致
        all_trading_days = [
            d.strftime('%Y-%m-%d') for d in self.db['stock_price'].distinct(
                'date',
                {'date': {'$gte': _q(start_date), '$lte': _q(end_date)}}
            )
        ]
        all_trading_days.sort()
        
        print(f"交易日數: {len(all_trading_days)}\n")
        
        # 執行回測
        pending = None      # (選股日, selections) —— 延後到下一個交易日才成交
        for date in tqdm(all_trading_days, desc="回測進度"):
            # 先處理上一輪待成交的再平衡(T+1 進場,避免用當日收盤算的訊號在當日收盤成交)
            if pending is not None:
                sel_date, sel = pending
                pending = None
                self.rebalance(date, sel)

            # 長期無報價的持股強制出場
            self._handle_stale_positions(date)

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
                
                # 再平衡:延後 entry_lag 個交易日成交(0 表示維持同日,僅供對照)
                if self.entry_lag > 0:
                    pending = (date, selections)
                else:
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
            'avg_loss': avg_loss,
            'total_fees': self.total_fees,
            'total_taxes': self.total_taxes,
            'cost_drag_pct': (self.total_fees + self.total_taxes) / self.initial_capital,
            'forced_exits': self.forced_exits
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
    
    # 回撤為負值,取絕對值比較幅度(負號代表回撤變小=改善)
    pct_dd = -safe_pct_change(abs(m21['max_drawdown']), abs(m20['max_drawdown']))
    print(f"{'最大回撤':<25} {m20['max_drawdown']:>14.2%} {m21['max_drawdown']:>14.2%} "
          f"{pct_dd:>14.2%}" if pct_dd != float('inf') else f"{'N/A':>15}")
    
    # 交易指標
    pct_wr = safe_pct_change(m21['win_rate'], m20['win_rate'])
    print(f"{'勝率':<25} {m20['win_rate']:>14.2%} {m21['win_rate']:>14.2%} "
          f"{pct_wr:>14.2%}" if pct_wr != float('inf') else f"{'N/A':>15}")
    
    pct_avg_win = safe_pct_change(m21['avg_win'], m20['avg_win'])
    print(f"{'平均獲利':<25} {m20['avg_win']:>14.2%} {m21['avg_win']:>14.2%} "
          f"{pct_avg_win:>14.2%}" if pct_avg_win != float('inf') else f"{'N/A':>15}")
    
    # 平均虧損為負值,同上取絕對值
    pct_avg_loss = -safe_pct_change(abs(m21['avg_loss']), abs(m20['avg_loss']))
    print(f"{'平均虧損':<25} {m20['avg_loss']:>14.2%} {m21['avg_loss']:>14.2%} "
          f"{pct_avg_loss:>14.2%}" if pct_avg_loss != float('inf') else f"{'N/A':>15}")
    
    print(f"{'總交易次數':<25} {m20['total_trades']:>15} {m21['total_trades']:>15} "
          f"{m21['total_trades'] - m20['total_trades']:>15}")

    for lbl, key in (('手續費合計', 'total_fees'), ('證交稅合計', 'total_taxes'),
                     ('強制出場次數', 'forced_exits')):
        if key in m20 or key in m21:
            print(f"{lbl:<25} {m20.get(key, 0):>15,.0f} {m21.get(key, 0):>15,.0f}")
    
    print(f"\n{'='*80}\n")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='v2.1 整合策略回測')
    parser.add_argument('--start-date', type=str, default='2022-01-01', help='開始日期')
    parser.add_argument('--end-date', type=str, default='2024-12-31', help='結束日期')
    parser.add_argument('--initial-capital', type=float, default=10_000_000, help='初始資金')
    parser.add_argument('--rebalance-frequency', type=str, default='monthly', choices=['monthly','quarterly','semiannual'], help='再平衡頻率(monthly/quarterly/semiannual)')
    parser.add_argument('--output', type=str, default='backtest_v21_results.json', help='輸出檔案')
    parser.add_argument('--fee-rate', type=float, default=0.001425, help='手續費率(公定 0.1425%%)')
    parser.add_argument('--fee-discount', type=float, default=0.6, help='手續費折扣(6 折=0.6)')
    parser.add_argument('--tax-rate', type=float, default=0.003, help='證交稅率(賣出 0.3%%)')
    parser.add_argument('--no-cost', action='store_true', help='關閉所有交易成本(對照用)')
    parser.add_argument('--quality-source', choices=['none', 'fundamental', 'legacy'],
                        default='fundamental',
                        help='quality 因子來源:none=不用 / fundamental=財報落後後的真序列 '
                             '/ legacy=stock_factors 常數(有前視,僅對照)')
    parser.add_argument('--entry-lag', type=int, default=1,
                        help='進場延後幾個交易日(0=同日成交,有同棒前視)')
    parser.add_argument('--stale-exit-days', type=int, default=20,
                        help='連續無報價幾日後強制出場')
    
    parser.add_argument('--momentum-filter', type=float, default=None,
                        help='把動能改當篩選器:先留動能前 N%%(如 0.5),再只用 '
                             'value/quality 排序。不給則維持動能當加權排序因子。'
                             '依據:2026-08-12 IC 分析顯示動能是 EXTREME_ONLY')
    parser.add_argument('--weights', type=str, default=None,
                        help='覆寫三大類權重,格式 momentum:value:quality(如 0.2:0.5:0.3),'
                             '會自動正規化為總和 1')

    args = parser.parse_args()

    def _tune(bt):
        """把 CLI 的策略層設定套到兩個 strategy 實例上。"""
        strats = [bt.strategy_v20, bt.strategy_v21.factor_strategy]
        if args.momentum_filter is not None:
            for s in strats:
                s.momentum_filter_pct = args.momentum_filter
            print(f"✓ 動能改當篩選器:保留前 {args.momentum_filter:.0%},"
                  f"排序僅用 value/quality")
        if args.weights:
            parts = [float(x) for x in args.weights.split(':')]
            if len(parts) != 3:
                raise ValueError("--weights 需三個值:momentum:value:quality")
            tot = sum(parts)
            if tot <= 0:
                raise ValueError("--weights 總和必須 > 0")
            w = dict(zip(('momentum', 'value', 'quality'), (p / tot for p in parts)))
            for s in strats:
                for cat, val in w.items():
                    if cat in s.factor_config:
                        s.factor_config[cat]['weight'] = val
            print("✓ 權重覆寫:" + ", ".join(f"{k} {v:.0%}" for k, v in w.items()))
        return bt

    cost_kw = dict(fee_rate=args.fee_rate, fee_discount=args.fee_discount,
                   tax_rate=args.tax_rate,
                   quality_source=args.quality_source,
                   entry_lag=args.entry_lag,
                   stale_exit_days=args.stale_exit_days)
    if args.no_cost:
        cost_kw.update(fee_rate=0.0, fee_discount=0.0, tax_rate=0.0, min_fee=0.0)
        print('⚠️  已關閉交易成本(--no-cost),結果不可作為決策依據')
    
    # 連接資料庫
    print("連接 MongoDB...")
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 回測 v2.0
    print("\n執行 v2.0 回測...")
    backtester_v20 = BacktestV21(
        db,
        initial_capital=args.initial_capital,
        rebalance_frequency=args.rebalance_frequency,
        **cost_kw
    )
    _tune(backtester_v20)
    results_v20 = backtester_v20.run(args.start_date, args.end_date, strategy_version='v2.0')
    
    # 回測 v2.1
    print("\n執行 v2.1 回測...")
    backtester_v21 = BacktestV21(
        db,
        initial_capital=args.initial_capital,
        rebalance_frequency=args.rebalance_frequency,
        **cost_kw
    )
    _tune(backtester_v21)
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
