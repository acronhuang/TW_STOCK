#!/usr/bin/env python3
"""
Backtest 模組 - 回測執行引擎

核心功能:
- 從 MongoDB 載入歷史數據
- 執行策略回測
- 生成績效報告
- 視覺化結果
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

import pandas as pd
import numpy as np
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.backtesting.portfolio import Portfolio
from src.backtesting.strategy import Strategy
from src.backtesting.performance import PerformanceCalculator, PerformanceMetrics


class Backtest:
    """
    回測引擎
    
    使用方式:
    ```python
    from src.backtesting import Backtest, MovingAverageCrossover
    
    # 建立策略
    strategy = MovingAverageCrossover()
    strategy.setup(short_window=5, long_window=20)
    
    # 建立回測
    bt = Backtest(
        strategy=strategy,
        symbols=['2330', '2317'],
        start_date='2023-01-01',
        end_date='2023-12-31',
        initial_cash=1_000_000
    )
    
    # 執行回測
    results = bt.run()
    print(results['metrics'])
    ```
    """
    
    def __init__(self,
                 strategy: Strategy,
                 symbols: List[str],
                 start_date: str,
                 end_date: str,
                 initial_cash: float = 1_000_000,
                 position_size: float = 0.2,
                 commission_rate: float = 0.003,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        """
        初始化回測引擎
        
        Args:
            strategy: 交易策略物件
            symbols: 股票代碼列表
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            initial_cash: 初始資金
            position_size: 單筆倉位大小（佔總資金比例，0.2 = 20%）
            commission_rate: 手續費率
            mongo_uri: MongoDB 連接字串
            db_name: 資料庫名稱
        """
        self.strategy = strategy
        self.symbols = symbols
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_cash = initial_cash
        self.position_size = position_size
        self.commission_rate = commission_rate
        
        # MongoDB
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        
        # 投資組合
        self.portfolio = Portfolio(initial_cash=initial_cash, commission_rate=commission_rate)
        
        # 數據
        self.data = None
        
        # 日誌
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """設定日誌"""
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        logger.addHandler(console_handler)
        
        return logger
    
    def load_data(self) -> pd.DataFrame:
        """
        從 MongoDB 載入歷史數據
        
        Returns:
            DataFrame with columns: date, symbol, open, high, low, close, volume, adj_close, ...
        """
        self.logger.info(f"載入數據: {self.symbols}, {self.start_date.date()} ~ {self.end_date.date()}")
        
        # 查詢條件
        query = {
            'symbol': {'$in': self.symbols},
            'date': {
                '$gte': self.start_date,
                '$lte': self.end_date
            }
        }
        
        # 從 stock_price 集合載入
        cursor = self.db.stock_price.find(query).sort('date', 1)
        
        records = []
        for doc in cursor:
            # 轉換 Decimal128 為 float
            record = {
                'date': doc['date'],
                'symbol': doc['symbol'],
                'open': self._to_float(doc.get('open', 0)),
                'high': self._to_float(doc.get('high', 0)),
                'low': self._to_float(doc.get('low', 0)),
                'close': self._to_float(doc.get('close', 0)),
                'volume': doc.get('volume', 0),
                'adj_close': self._to_float(doc.get('adj_close', doc.get('close', 0))),
            }
            
            # 可選欄位
            if 'pe_ratio' in doc:
                record['pe_ratio'] = self._to_float(doc['pe_ratio'])
            if 'pb_ratio' in doc:
                record['pb_ratio'] = self._to_float(doc['pb_ratio'])
            
            records.append(record)
        
        df = pd.DataFrame(records)
        
        if df.empty:
            raise ValueError("無數據！請檢查股票代碼和日期範圍")
        
        self.logger.info(f"載入完成: {len(df)} 筆記錄")
        self.data = df
        return df
    
    def _to_float(self, value) -> float:
        """統一轉換為 float"""
        if value is None:
            return 0.0
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        return float(value)
    
    def run(self) -> Dict:
        """
        執行回測
        
        Returns:
            {
                'metrics': PerformanceMetrics,
                'equity_curve': DataFrame,
                'trades': List[Trade],
                'strategy': Strategy
            }
        """
        self.logger.info(f"開始回測: {self.strategy.name}")
        self.logger.info(f"策略參數: {self.strategy.params}")
        
        # 載入數據
        if self.data is None:
            self.load_data()
        
        # 取得交易日期
        trading_dates = sorted(self.data['date'].unique())
        self.logger.info(f"交易日期: {len(trading_dates)} 天")
        
        # 逐日執行
        for current_date in trading_dates:
            # 取得當日之前的所有數據（用於計算指標）
            historical_data = self.data[self.data['date'] <= current_date]
            
            # 生成交易信號
            signals = self.strategy.generate_signals(current_date, historical_data)
            
            # 取得當日價格
            current_prices = {}
            for symbol in self.symbols:
                symbol_data = historical_data[
                    (historical_data['symbol'] == symbol) & 
                    (historical_data['date'] == current_date)
                ]
                if not symbol_data.empty:
                    current_prices[symbol] = symbol_data.iloc[0]['adj_close']
            
            # 執行交易
            self._execute_signals(current_date, signals, current_prices)
            
            # 記錄權益曲線
            self.portfolio.record_equity(current_date, current_prices)
        
        self.logger.info("回測完成")
        
        # 計算績效指標
        metrics = PerformanceCalculator.calculate(
            equity_curve=self.portfolio.equity_curve,
            trades=self.portfolio.trades,
            initial_cash=self.initial_cash
        )
        
        # 返回結果
        results = {
            'metrics': metrics,
            'equity_curve': pd.DataFrame(self.portfolio.equity_curve),
            'trades': self.portfolio.trades,
            'strategy': self.strategy
        }
        
        return results
    
    def _execute_signals(self, date: datetime, signals: Dict[str, str], prices: Dict[str, float]):
        """
        執行交易信號
        
        Args:
            date: 當前日期
            signals: {symbol: signal} 字典
            prices: {symbol: price} 字典
        """
        for symbol, signal in signals.items():
            if symbol not in prices:
                continue
            
            price = prices[symbol]
            if price <= 0:
                continue
            
            if signal == 'BUY':
                # 檢查是否已持有
                if not self.portfolio.has_position(symbol):
                    # 計算可買股數
                    position_value = self.portfolio.cash * self.position_size
                    shares = int(position_value / price / 1000) * 1000  # 台股以 1000 股為單位
                    
                    if shares >= 1000:
                        self.portfolio.buy(date, symbol, shares, price)
            
            elif signal == 'SELL':
                # 如果持有，全部賣出
                if self.portfolio.has_position(symbol):
                    position = self.portfolio.get_position(symbol)
                    self.portfolio.sell(date, symbol, position.shares, price)
    
    def summary(self):
        """列印回測摘要"""
        if not self.portfolio.equity_curve:
            self.logger.warning("尚未執行回測")
            return
        
        metrics = PerformanceCalculator.calculate(
            equity_curve=self.portfolio.equity_curve,
            trades=self.portfolio.trades,
            initial_cash=self.initial_cash
        )
        
        print(metrics)
    
    def plot_equity_curve(self, save_path: Optional[str] = None):
        """
        繪製權益曲線
        
        Args:
            save_path: 儲存路徑（可選）
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            self.logger.error("需要安裝 matplotlib: pip install matplotlib")
            return
        
        if not self.portfolio.equity_curve:
            self.logger.warning("尚未執行回測")
            return
        
        df = pd.DataFrame(self.portfolio.equity_curve)
        df['date'] = pd.to_datetime(df['date'])
        
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # 繪製權益曲線
        ax.plot(df['date'], df['equity'], label='Portfolio Equity', linewidth=2)
        ax.axhline(y=self.initial_cash, color='gray', linestyle='--', label='Initial Cash')
        
        # 格式化
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Equity (TWD)', fontsize=12)
        ax.set_title(f'Equity Curve - {self.strategy.name}', fontsize=14, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 格式化 x 軸日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"權益曲線已儲存: {save_path}")
        else:
            plt.show()
