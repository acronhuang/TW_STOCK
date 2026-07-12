#!/usr/bin/env python3
"""
Momentum Factors 模組 - 動能因子計算

計算基於價格趨勢的因子:
- 1M Return（1 個月報酬率）
- 3M Return（3 個月報酬率）
- 6M Return（6 個月報酬率）
- 12M Return（12 個月報酬率）
- RSI（相對強弱指標）
- Price Momentum（價格動能）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from bson.decimal128 import Decimal128


class MomentumFactors:
    """動能因子計算器"""
    
    def __init__(self, db):
        """
        Args:
            db: MongoDB database instance
        """
        self.db = db
    
    def _to_float(self, value) -> float:
        """統一轉換為 float"""
        if value is None:
            return None
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        return float(value)
    
    def calculate_return(self, symbol: str, end_date: datetime, 
                        days: int) -> Optional[float]:
        """
        計算指定期間的報酬率
        
        Return = ((P_end - P_start) / P_start) × 100%
        
        Args:
            symbol: 股票代碼
            end_date: 結束日期
            days: 回溯天數
        
        Returns:
            報酬率 (%) 或 None
        """
        start_date = end_date - timedelta(days=days)
        
        # 取得期間內的價格數據
        prices = list(self.db.stock_price.find({
            'symbol': symbol,
            'date': {'$gte': start_date, '$lte': end_date}
        }).sort('date', 1))
        
        if len(prices) < 2:
            return None
        
        # 取得起始和結束價格（使用調整後收盤價）
        start_price = self._to_float(prices[0].get('adj_close', prices[0].get('close')))
        end_price = self._to_float(prices[-1].get('adj_close', prices[-1].get('close')))
        
        if start_price and start_price > 0 and end_price is not None:
            return ((end_price - start_price) / start_price) * 100

        return None
    
    def calculate_1m_return(self, symbol: str, date: datetime) -> Optional[float]:
        """計算 1 個月報酬率"""
        return self.calculate_return(symbol, date, days=30)
    
    def calculate_3m_return(self, symbol: str, date: datetime) -> Optional[float]:
        """計算 3 個月報酬率"""
        return self.calculate_return(symbol, date, days=90)
    
    def calculate_6m_return(self, symbol: str, date: datetime) -> Optional[float]:
        """計算 6 個月報酬率"""
        return self.calculate_return(symbol, date, days=180)
    
    def calculate_12m_return(self, symbol: str, date: datetime) -> Optional[float]:
        """計算 12 個月報酬率"""
        return self.calculate_return(symbol, date, days=365)
    
    def calculate_rsi(self, symbol: str, date: datetime, period: int = 14) -> Optional[float]:
        """
        計算 RSI（相對強弱指標）
        
        RSI = 100 - (100 / (1 + RS))
        RS = 平均漲幅 / 平均跌幅
        
        Args:
            symbol: 股票代碼
            date: 計算日期
            period: RSI 週期（default: 14）
        
        Returns:
            RSI 值 (0-100) 或 None
        """
        start_date = date - timedelta(days=period * 2)  # 取更多數據以確保足夠樣本
        
        # 取得價格數據
        prices = list(self.db.stock_price.find({
            'symbol': symbol,
            'date': {'$gte': start_date, '$lte': date}
        }).sort('date', 1))
        
        if len(prices) < period + 1:
            return None
        
        # 提取調整後收盤價
        close_prices = [self._to_float(p.get('adj_close', p.get('close'))) for p in prices]
        
        # 計算價格變化
        deltas = np.diff(close_prices)
        
        # 分離漲跌
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # 計算平均漲跌幅（使用最近 period 筆數據）
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0  # 完全沒有下跌
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_price_momentum(self, symbol: str, date: datetime, 
                                 lookback_days: int = 252) -> Optional[float]:
        """
        計算價格動能指標
        
        Price Momentum = (當前價格 / N日前價格) - 1
        
        常用於捕捉中長期趨勢
        
        Args:
            symbol: 股票代碼
            date: 計算日期
            lookback_days: 回溯天數（default: 252 = 1年）
        
        Returns:
            Price momentum 或 None
        """
        return self.calculate_return(symbol, date, lookback_days)
    
    def calculate_volatility(self, symbol: str, date: datetime, 
                            window: int = 30) -> Optional[float]:
        """
        計算價格波動率（標準差）
        
        Volatility = std(returns) × sqrt(252)
        
        Args:
            symbol: 股票代碼
            date: 計算日期
            window: 計算窗口（default: 30 天）
        
        Returns:
            年化波動率 (%) 或 None
        """
        start_date = date - timedelta(days=window * 2)
        
        prices = list(self.db.stock_price.find({
            'symbol': symbol,
            'date': {'$gte': start_date, '$lte': date}
        }).sort('date', 1))
        
        if len(prices) < window:
            return None
        
        # 提取最近 window 筆收盤價（過濾 None）
        close_prices = [self._to_float(p.get('adj_close', p.get('close'))) for p in prices[-window:]]
        close_prices = [p for p in close_prices if p is not None]

        if len(close_prices) < 2:
            return None

        # 計算日報酬率
        close_arr = np.array(close_prices, dtype=float)
        returns = np.diff(close_arr) / close_arr[:-1]
        
        # 計算標準差並年化
        volatility = np.std(returns) * np.sqrt(252) * 100
        
        return volatility
    
    # 乖離窗：20短/60季線/120半年線/240年線
    MA_BIAS_WINDOWS = (20, 60, 120, 240)
    MA_LONG_WINDOWS = (60, 120, 240)      # 季線/半年線/年線(長期趨勢)

    def calculate_ma_bias(self, symbol: str, date: datetime,
                          windows=None) -> Dict:
        """移動平均線乖離率 % = (收盤 - MA_N) / MA_N × 100。
        正值=價在均線上方(偏多/超買)，負值=下方(偏空/超賣)。
        含 20(短)/60(季線)/120(半年線)/240(年線)。截至 date。"""
        windows = windows or self.MA_BIAS_WINDOWS
        maxw = max(windows)
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$lte': date}},
            {'close': 1}).sort('date', -1).limit(maxw))
        closes = [self._to_float(p.get('close')) for p in prices]
        closes = [c for c in closes if c]          # 最新在前
        out = {f'ma_bias_{w}': None for w in windows}
        if not closes:
            return out
        c = closes[0]
        for w in windows:
            if len(closes) >= w:
                ma = sum(closes[:w]) / w
                out[f'ma_bias_{w}'] = round((c - ma) / ma * 100, 2) if ma else None
        return out

    def calculate_ma_long_trend(self, symbol: str, date: datetime) -> Dict:
        """長期均線(季線60/半年線120/年線240)趨勢位置：
          ma_above_long : 現價站上幾條長均線(0~3)，越多越多頭格局
          ma_long_trend : 長期排列方向 1=長多(60>120>240) / -1=長空(60<120<240) / 0=糾結
        年線是台股多空分界，底部型態在年線上方較可靠。截至 date。"""
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$lte': date}},
            {'close': 1}).sort('date', -1).limit(max(self.MA_LONG_WINDOWS)))
        closes = [self._to_float(p.get('close')) for p in prices]
        closes = [c for c in closes if c]
        if not closes:
            return {'ma_above_long': None, 'ma_long_trend': None}
        c = closes[0]
        mas = {w: sum(closes[:w]) / w for w in self.MA_LONG_WINDOWS if len(closes) >= w}
        if not mas:
            return {'ma_above_long': None, 'ma_long_trend': None}
        above = sum(1 for w in mas if c > mas[w])
        trend = 0
        if len(mas) == 3:
            v = [mas[60], mas[120], mas[240]]
            if v[0] > v[1] > v[2]:
                trend = 1
            elif v[0] < v[1] < v[2]:
                trend = -1
        return {'ma_above_long': above, 'ma_long_trend': trend}

    def calculate_inst_streak(self, symbol: str, date: datetime,
                              lookback: int = 40) -> Dict:
        """三大法人連續買/賣超天數(外資/投信)。+N=連N日買超, -N=連N日賣超, 0=中性/無資料。
        以連續『有資料的交易日』計(institutional_flow key=stock_id)。截至 date。"""
        docs = list(self.db.institutional_flow.find(
            {'stock_id': symbol, 'date': {'$lte': date}},
            {'foreign_net': 1, 'trust_net': 1}).sort('date', -1).limit(lookback))

        def streak(key):
            n, sign = 0, 0
            for d in docs:
                v = self._to_float(d.get(key))
                if v is None or v == 0:
                    break
                s = 1 if v > 0 else -1
                if sign == 0:
                    sign = s
                elif s != sign:
                    break
                n += 1
            return sign * n

        return {'foreign_streak': streak('foreign_net'),
                'trust_streak': streak('trust_net')}

    def calculate_all_momentum_factors(self, symbol: str, date: datetime) -> Dict:
        """
        計算所有動能因子
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            {
                'return_1m': float,
                'return_3m': float,
                'return_6m': float,
                'return_12m': float,
                'rsi_14': float,
                'volatility_30d': float
            }
        """
        return {
            'date': date,
            'symbol': symbol,
            'return_1m': self.calculate_1m_return(symbol, date),
            'return_3m': self.calculate_3m_return(symbol, date),
            'return_6m': self.calculate_6m_return(symbol, date),
            'return_12m': self.calculate_12m_return(symbol, date),
            'rsi_14': self.calculate_rsi(symbol, date, period=14),
            'volatility_30d': self.calculate_volatility(symbol, date, window=30),
            **self.calculate_ma_bias(symbol, date),
            **self.calculate_ma_long_trend(symbol, date),
            **self.calculate_inst_streak(symbol, date),
        }
    
    def batch_calculate(self, symbols: List[str], start_date: datetime, 
                        end_date: datetime) -> pd.DataFrame:
        """
        批次計算動能因子
        
        Args:
            symbols: 股票代碼列表
            start_date: 開始日期
            end_date: 結束日期
        
        Returns:
            DataFrame with momentum factors
        """
        results = []
        
        # 取得所有交易日
        trading_dates = self.db.stock_price.distinct('date', {
            'date': {'$gte': start_date, '$lte': end_date}
        })
        
        for date in sorted(trading_dates):
            for symbol in symbols:
                factors = self.calculate_all_momentum_factors(symbol, date)
                results.append(factors)
        
        return pd.DataFrame(results)
