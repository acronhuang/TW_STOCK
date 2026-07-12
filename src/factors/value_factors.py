#!/usr/bin/env python3
"""
Value Factors 模組 - 價值因子計算

計算基於估值的因子:
- P/E Ratio（本益比）
- P/B Ratio（股價淨值比）
- Dividend Yield（股息殖利率）
- EV/EBITDA（企業價值倍數）
- Earnings Yield（盈餘殖利率）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from bson.decimal128 import Decimal128


class ValueFactors:
    """價值因子計算器"""
    
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
    
    def calculate_pe_ratio(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算本益比 (P/E Ratio)
        
        P/E = 股價 / EPS
        EPS = 淨利 / 流通股數
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            P/E ratio 或 None
        """
        # 1. 取得股價
        price_doc = self.db.stock_price.find_one({
            'symbol': symbol,
            'date': date
        })
        
        if not price_doc:
            return None
        
        price = self._to_float(price_doc.get('close'))
        if not price or price <= 0:
            return None
        
        # 2. 取得最新財報的淨利
        financial_doc = self.db.financial_reports.find_one(
            {
                'symbol': symbol,
                'incomeStatement.netIncome': {'$exists': True, '$ne': None, '$gt': 0}
            },
            sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
        )
        
        if not financial_doc:
            return None
        
        income_statement = financial_doc.get('incomeStatement', {})
        net_income = self._to_float(income_statement.get('netIncome'))
        
        if not net_income or net_income <= 0:
            return None
        
        # 3. 取得流通股數
        stock_info = self.db.taiwan_stock_info.find_one(
            {'stock_id': symbol},
            sort=[('date', -1)]
        )
        
        if not stock_info:
            return None
        
        outstanding_shares = self._to_float(stock_info.get('outstanding_shares'))
        
        if not outstanding_shares or outstanding_shares <= 0:
            return None
        
        # 4. 計算 EPS 和 PE
        # outstanding_shares 單位是千股，需要乘以 1000 轉為股數
        eps = net_income / (outstanding_shares * 1000)
        
        if eps <= 0:
            return None
        
        pe_ratio = price / eps
        
        # 過濾極端值
        if pe_ratio > 0 and pe_ratio < 1000:
            return pe_ratio
        
        return None
    
    def calculate_pb_ratio(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算股價淨值比 (P/B Ratio)
        
        P/B = 股價 / 每股淨值
        每股淨值 = 股東權益 / 流通股數
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            P/B ratio 或 None
        """
        # 1. 取得股價
        price_doc = self.db.stock_price.find_one({
            'symbol': symbol,
            'date': date
        })
        
        if not price_doc:
            return None
        
        price = self._to_float(price_doc.get('close'))
        if not price or price <= 0:
            return None
        
        # 2. 取得最新財報的股東權益
        financial_doc = self.db.financial_reports.find_one(
            {
                'symbol': symbol,
                'balanceSheet.equity': {'$exists': True, '$ne': None, '$gt': 0}
            },
            sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
        )
        
        if not financial_doc:
            return None
        
        balance_sheet = financial_doc.get('balanceSheet', {})
        equity = self._to_float(balance_sheet.get('equity'))
        
        if not equity or equity <= 0:
            return None
        
        # 3. 取得流通股數
        stock_info = self.db.taiwan_stock_info.find_one(
            {'stock_id': symbol},
            sort=[('date', -1)]
        )
        
        if not stock_info:
            return None
        
        outstanding_shares = self._to_float(stock_info.get('outstanding_shares'))
        
        if not outstanding_shares or outstanding_shares <= 0:
            return None
        
        # 4. 計算每股淨值和 PB
        # outstanding_shares 單位是千股，需要乘以 1000 轉為股數
        book_value_per_share = equity / (outstanding_shares * 1000)
        
        if book_value_per_share <= 0:
            return None
        
        pb_ratio = price / book_value_per_share
        
        # 過濾極端值
        if pb_ratio > 0 and pb_ratio < 100:
            return pb_ratio
        
        return None
    
    def calculate_dividend_yield(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算股息殖利率 (Dividend Yield)
        
        Dividend Yield = (過去一年現金股利 / 股價) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Dividend yield (%) 或 None
        """
        # 取得當日股價
        price_doc = self.db.stock_price.find_one({
            'symbol': symbol,
            'date': date
        })
        
        if not price_doc:
            return None
        
        price = self._to_float(price_doc.get('close'))
        
        if not price or price <= 0:
            return None
        
        # 取得過去一年的股利資料
        year = date.year - 1  # 以前一年度的股利為準
        
        dividend_doc = self.db.dividend_results.find_one({
            'stock_id': symbol,
            'year': year
        })
        
        if not dividend_doc:
            return None
        
        # 現金股利
        cash_dividend = self._to_float(dividend_doc.get('cash_dividend', 0))
        
        if cash_dividend > 0:
            return (cash_dividend / price) * 100
        
        return None
    
    def calculate_earnings_yield(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算盈餘殖利率 (Earnings Yield)
        
        Earnings Yield = (EPS / 股價) × 100% = 1 / P/E
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Earnings yield (%) 或 None
        """
        pe = self.calculate_pe_ratio(symbol, date)
        
        if pe and pe > 0:
            return (1 / pe) * 100
        
        return None
    
    def calculate_all_value_factors(self, symbol: str, date: datetime) -> Dict:
        """
        計算所有價值因子
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            {
                'pe_ratio': float,
                'pb_ratio': float,
                'dividend_yield': float,
                'earnings_yield': float
            }
        """
        return {
            'date': date,
            'symbol': symbol,
            'pe_ratio': self.calculate_pe_ratio(symbol, date),
            'pb_ratio': self.calculate_pb_ratio(symbol, date),
            'dividend_yield': self.calculate_dividend_yield(symbol, date),
            'earnings_yield': self.calculate_earnings_yield(symbol, date)
        }
    
    def batch_calculate(self, symbols: List[str], start_date: datetime, 
                        end_date: datetime) -> pd.DataFrame:
        """
        批次計算價值因子
        
        Args:
            symbols: 股票代碼列表
            start_date: 開始日期
            end_date: 結束日期
        
        Returns:
            DataFrame with value factors
        """
        results = []
        
        # 取得所有交易日
        trading_dates = self.db.stock_price.distinct('date', {
            'date': {'$gte': start_date, '$lte': end_date}
        })
        
        for date in sorted(trading_dates):
            for symbol in symbols:
                factors = self.calculate_all_value_factors(symbol, date)
                results.append(factors)
        
        return pd.DataFrame(results)
