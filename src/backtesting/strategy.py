#!/usr/bin/env python3
"""
Strategy 模組 - 交易策略基類

提供策略接口定義，方便繼承實現自定義策略
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


class Strategy(ABC):
    """
    交易策略基類
    
    子類需實現:
    - setup(): 策略初始化
    - generate_signals(): 生成交易信號
    """
    
    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.params = {}
        self.data = {}
    
    @abstractmethod
    def setup(self, **kwargs):
        """
        策略初始化設定
        
        Args:
            **kwargs: 策略參數
        """
        pass
    
    @abstractmethod
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成交易信號
        
        Args:
            date: 當前日期
            data: 歷史數據（DataFrame，columns: date, symbol, open, high, low, close, volume, adj_close, ...）
        
        Returns:
            Dict[symbol, signal]: 信號字典
                signal 可為: 'BUY', 'SELL', 'HOLD'
        """
        pass
    
    def __repr__(self):
        return f"<Strategy: {self.name}>"


class MovingAverageCrossover(Strategy):
    """
    均線交叉策略
    
    信號邏輯:
    - 短均線上穿長均線 → 買入
    - 短均線下穿長均線 → 賣出
    """
    
    def __init__(self):
        super().__init__(name="MA Crossover")
        self.short_window = 5
        self.long_window = 20
    
    def setup(self, short_window: int = 5, long_window: int = 20):
        """
        設定均線參數
        
        Args:
            short_window: 短均線週期
            long_window: 長均線週期
        """
        self.short_window = short_window
        self.long_window = long_window
        self.params = {
            'short_window': short_window,
            'long_window': long_window
        }
    
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成均線交叉信號
        
        Args:
            date: 當前日期
            data: 包含價格數據的 DataFrame
        
        Returns:
            {symbol: signal} 字典
        """
        signals = {}
        
        # 取得所有股票代碼
        symbols = data['symbol'].unique()
        
        for symbol in symbols:
            # 過濾該股票數據
            stock_data = data[data['symbol'] == symbol].copy()
            stock_data = stock_data.sort_values('date')
            
            # 需要足夠的數據計算長均線
            if len(stock_data) < self.long_window:
                continue
            
            # 計算均線
            stock_data['ma_short'] = stock_data['adj_close'].rolling(window=self.short_window).mean()
            stock_data['ma_long'] = stock_data['adj_close'].rolling(window=self.long_window).mean()
            
            # 取得最近兩日數據
            recent = stock_data.tail(2)
            if len(recent) < 2:
                continue
            
            prev_row = recent.iloc[0]
            curr_row = recent.iloc[1]
            
            # 確保當前日期是我們要的日期
            if curr_row['date'] != date:
                continue
            
            # 檢查是否有效
            if pd.isna(curr_row['ma_short']) or pd.isna(curr_row['ma_long']):
                continue
            
            # 黃金交叉（短均線上穿長均線）
            if (prev_row['ma_short'] <= prev_row['ma_long'] and 
                curr_row['ma_short'] > curr_row['ma_long']):
                signals[symbol] = 'BUY'
            
            # 死亡交叉（短均線下穿長均線）
            elif (prev_row['ma_short'] >= prev_row['ma_long'] and 
                  curr_row['ma_short'] < curr_row['ma_long']):
                signals[symbol] = 'SELL'
            
            else:
                signals[symbol] = 'HOLD'
        
        return signals


class RSIMeanReversion(Strategy):
    """
    RSI 均值回歸策略
    
    信號邏輯:
    - RSI < 30 (超賣) → 買入
    - RSI > 70 (超買) → 賣出
    """
    
    def __init__(self):
        super().__init__(name="RSI Mean Reversion")
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
    
    def setup(self, rsi_period: int = 14, oversold: float = 30, overbought: float = 70):
        """
        設定 RSI 參數
        
        Args:
            rsi_period: RSI 計算週期
            oversold: 超賣閾值
            overbought: 超買閾值
        """
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.params = {
            'rsi_period': rsi_period,
            'oversold': oversold,
            'overbought': overbought
        }
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """
        計算 RSI 指標
        
        Args:
            prices: 價格序列
            period: 週期
        
        Returns:
            RSI 值序列
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成 RSI 信號
        
        Args:
            date: 當前日期
            data: 包含價格數據的 DataFrame
        
        Returns:
            {symbol: signal} 字典
        """
        signals = {}
        
        symbols = data['symbol'].unique()
        
        for symbol in symbols:
            stock_data = data[data['symbol'] == symbol].copy()
            stock_data = stock_data.sort_values('date')
            
            # 需要足夠的數據
            if len(stock_data) < self.rsi_period + 1:
                continue
            
            # 計算 RSI
            stock_data['rsi'] = self._calculate_rsi(stock_data['adj_close'], self.rsi_period)
            
            # 取得當前日期的數據
            curr_data = stock_data[stock_data['date'] == date]
            if curr_data.empty:
                continue
            
            curr_rsi = curr_data['rsi'].iloc[0]
            
            # 檢查是否有效
            if pd.isna(curr_rsi):
                continue
            
            # 生成信號
            if curr_rsi < self.oversold:
                signals[symbol] = 'BUY'  # 超賣，買入
            elif curr_rsi > self.overbought:
                signals[symbol] = 'SELL'  # 超買，賣出
            else:
                signals[symbol] = 'HOLD'
        
        return signals


class ValueMomentum(Strategy):
    """
    價值-動能組合策略
    
    信號邏輯:
    - 低 P/E + 正動能 → 買入
    - 高 P/E 或負動能 → 賣出
    """
    
    def __init__(self):
        super().__init__(name="Value-Momentum")
        self.pe_threshold = 15
        self.momentum_days = 60
    
    def setup(self, pe_threshold: float = 15, momentum_days: int = 60):
        """
        設定參數
        
        Args:
            pe_threshold: P/E 閾值（低於此值視為價值股）
            momentum_days: 動能計算天數
        """
        self.pe_threshold = pe_threshold
        self.momentum_days = momentum_days
        self.params = {
            'pe_threshold': pe_threshold,
            'momentum_days': momentum_days
        }
    
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成價值-動能信號
        
        Args:
            date: 當前日期
            data: 包含價格、P/E 等數據的 DataFrame
        
        Returns:
            {symbol: signal} 字典
        """
        signals = {}
        
        symbols = data['symbol'].unique()
        
        for symbol in symbols:
            stock_data = data[data['symbol'] == symbol].copy()
            stock_data = stock_data.sort_values('date')
            
            # 需要足夠的數據
            if len(stock_data) < self.momentum_days:
                continue
            
            # 取得當前數據
            curr_data = stock_data[stock_data['date'] == date]
            if curr_data.empty:
                continue
            
            curr_row = curr_data.iloc[0]
            
            # 檢查 P/E
            if 'pe_ratio' not in curr_row or pd.isna(curr_row['pe_ratio']):
                continue
            
            pe = curr_row['pe_ratio']
            
            # 計算動能（過去 N 天報酬率）
            past_data = stock_data.tail(self.momentum_days + 1)
            if len(past_data) < 2:
                continue
            
            first_price = past_data.iloc[0]['adj_close']
            last_price = past_data.iloc[-1]['adj_close']
            
            if first_price == 0:
                continue
            
            momentum = ((last_price - first_price) / first_price) * 100
            
            # 信號邏輯
            if pe < self.pe_threshold and momentum > 0:
                signals[symbol] = 'BUY'  # 價值股 + 正動能
            elif pe > self.pe_threshold * 2 or momentum < -10:
                signals[symbol] = 'SELL'  # 高估或負動能
            else:
                signals[symbol] = 'HOLD'
        
        return signals
