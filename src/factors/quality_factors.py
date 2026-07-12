#!/usr/bin/env python3
"""
Quality Factors 模組 - 質量因子計算

計算基於財務健康度的因子:
- ROE（股東權益報酬率）
- ROA（資產報酬率）
- ROIC（投資資本報酬率）
- Profit Margin（淨利率）
- Operating Margin（營益率）
- Current Ratio（流動比率）
- Debt Ratio（負債比率）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from bson.decimal128 import Decimal128


class QualityFactors:
    """質量因子計算器"""
    
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
    
    def get_latest_financial_report(self, symbol: str, before_date: Optional[datetime] = None) -> Optional[Dict]:
        """
        取得最新財報

        查詢順序：
        1. quarterly_earnings（1,900+ 支，FinMind 季報，結構需轉換）
        2. financial_statements（192 支，已有 ratios 欄位）
        3. financial_reports（207 支，MOPS 來源）

        Args:
            symbol: 股票代碼
            before_date: 指定日期之前（可選）

        Returns:
            統一格式的財報文件或 None
        """
        query = {'symbol': symbol}

        # 首選: quarterly_earnings（覆蓋率最高 1,900+ 支）
        qe = self.db.quarterly_earnings.find_one(
            query, sort=[('year', -1), ('season', -1)]
        )
        if qe:
            inc = qe.get('income', {})
            bal = qe.get('balance', {})
            return {
                'symbol': symbol,
                'ratios': {
                    'roe': bal.get('roe'),
                    'roa': None,
                    'operatingMargin': inc.get('operating_margin'),
                    'netMargin': inc.get('net_margin'),
                },
                'incomeStatement': {
                    'revenue': inc.get('revenue'),
                    'operatingIncome': inc.get('operating_income'),
                    'netIncome': inc.get('net_income'),
                    'eps': inc.get('eps'),
                    'operatingMargin': inc.get('operating_margin'),
                    'netMargin': inc.get('net_margin'),
                },
                'balanceSheet': {
                    'equity': bal.get('total_equity'),
                    'totalAssets': bal.get('total_assets'),
                    'totalLiabilities': bal.get('total_liabilities'),
                    'currentAssets': bal.get('current_assets'),
                    'currentLiabilities': bal.get('current_liabilities'),
                    'debtRatio': (
                        bal['total_liabilities'] / bal['total_assets'] * 100
                        if bal.get('total_assets') and bal.get('total_liabilities')
                           and bal['total_assets'] > 0
                        else None
                    ),
                    'currentRatio': (
                        bal['current_assets'] / bal['current_liabilities']
                        if bal.get('current_assets') and bal.get('current_liabilities')
                           and bal['current_liabilities'] > 0
                        else None
                    ),
                },
                '_source': 'quarterly_earnings',
            }

        # 次選: financial_statements（含已計算 ratios/margins）
        report = self.db.financial_statements.find_one(
            query,
            sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
        )
        if report:
            return report

        # 末選: financial_reports（排除 netIncome=0 的無效資料）
        query['incomeStatement.netIncome'] = {'$gt': 0}
        report = self.db.financial_reports.find_one(
            query,
            sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
        )
        return report
    
    def calculate_roe(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算 ROE（股東權益報酬率）
        
        ROE = (淨利 / 平均股東權益) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            ROE (%) 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report:
            return None
        
        # 從 ratios 取得已計算的 ROE
        if 'ratios' in report and report['ratios']:
            roe = report['ratios'].get('roe')
            if roe is not None and float(roe) != 0:
                return float(roe)
        
        # 手動計算
        if 'incomeStatement' not in report or 'balanceSheet' not in report:
            return None
        
        net_income = self._to_float(report['incomeStatement'].get('netIncome'))
        equity = self._to_float(report['balanceSheet'].get('equity'))
        
        if net_income and equity and equity > 0:
            return (net_income / equity) * 100
        
        return None
    
    def calculate_roa(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算 ROA（資產報酬率）
        
        ROA = (淨利 / 平均總資產) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            ROA (%) 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report:
            return None
        
        # 從 ratios 取得已計算的 ROA
        if 'ratios' in report and report['ratios']:
            roa = report['ratios'].get('roa')
            if roa is not None and float(roa) != 0:
                return float(roa)
        
        # 手動計算
        if 'incomeStatement' not in report or 'balanceSheet' not in report:
            return None
        
        net_income = self._to_float(report['incomeStatement'].get('netIncome'))
        total_assets = self._to_float(report['balanceSheet'].get('totalAssets'))
        
        if net_income and total_assets and total_assets > 0:
            return (net_income / total_assets) * 100
        
        return None
    
    def calculate_profit_margin(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算淨利率（Profit Margin）
        
        Profit Margin = (淨利 / 營業收入) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Profit margin (%) 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report or 'incomeStatement' not in report:
            return None
        
        income_statement = report['incomeStatement']
        
        # 從已計算欄位取得
        net_margin = income_statement.get('netMargin')
        if net_margin is not None:
            return self._to_float(net_margin)
        
        # 手動計算
        net_income = self._to_float(income_statement.get('netIncome'))
        revenue = self._to_float(income_statement.get('revenue'))
        
        if net_income and revenue and revenue > 0:
            return (net_income / revenue) * 100
        
        return None
    
    def calculate_operating_margin(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算營益率（Operating Margin）
        
        Operating Margin = (營業利益 / 營業收入) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Operating margin (%) 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report or 'incomeStatement' not in report:
            return None
        
        income_statement = report['incomeStatement']
        
        # 從已計算欄位取得
        operating_margin = income_statement.get('operatingMargin')
        if operating_margin is not None:
            return self._to_float(operating_margin)
        
        # 手動計算
        operating_income = self._to_float(income_statement.get('operatingIncome'))
        revenue = self._to_float(income_statement.get('revenue'))
        
        if operating_income and revenue and revenue > 0:
            return (operating_income / revenue) * 100
        
        return None
    
    def calculate_current_ratio(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算流動比率（Current Ratio）
        
        Current Ratio = 流動資產 / 流動負債
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Current ratio 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report or 'balanceSheet' not in report:
            return None
        
        balance_sheet = report['balanceSheet']
        
        # 從已計算欄位取得
        current_ratio = balance_sheet.get('currentRatio')
        if current_ratio is not None:
            return self._to_float(current_ratio)
        
        # 手動計算
        current_assets = self._to_float(balance_sheet.get('currentAssets'))
        current_liabilities = self._to_float(balance_sheet.get('currentLiabilities'))
        
        if current_assets and current_liabilities and current_liabilities > 0:
            return current_assets / current_liabilities
        
        return None
    
    def calculate_debt_ratio(self, symbol: str, date: datetime) -> Optional[float]:
        """
        計算負債比率（Debt Ratio）
        
        Debt Ratio = (負債總計 / 資產總計) × 100%
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            Debt ratio (%) 或 None
        """
        report = self.get_latest_financial_report(symbol, before_date=date)
        
        if not report or 'balanceSheet' not in report:
            return None
        
        balance_sheet = report['balanceSheet']
        
        # 從已計算欄位取得
        debt_ratio = balance_sheet.get('debtRatio')
        if debt_ratio is not None:
            return self._to_float(debt_ratio)
        
        # 手動計算
        total_liabilities = self._to_float(balance_sheet.get('totalLiabilities'))
        total_assets = self._to_float(balance_sheet.get('totalAssets'))
        
        if total_liabilities and total_assets and total_assets > 0:
            return (total_liabilities / total_assets) * 100
        
        return None
    
    def calculate_all_quality_factors(self, symbol: str, date: datetime) -> Dict:
        """
        計算所有質量因子
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            {
                'roe': float,
                'roa': float,
                'profit_margin': float,
                'operating_margin': float,
                'current_ratio': float,
                'debt_ratio': float
            }
        """
        return {
            'date': date,
            'symbol': symbol,
            'roe': self.calculate_roe(symbol, date),
            'roa': self.calculate_roa(symbol, date),
            'profit_margin': self.calculate_profit_margin(symbol, date),
            'operating_margin': self.calculate_operating_margin(symbol, date),
            'current_ratio': self.calculate_current_ratio(symbol, date),
            'debt_ratio': self.calculate_debt_ratio(symbol, date)
        }
    
    def batch_calculate(self, symbols: List[str], start_date: datetime, 
                        end_date: datetime) -> pd.DataFrame:
        """
        批次計算質量因子
        
        Args:
            symbols: 股票代碼列表
            start_date: 開始日期
            end_date: 結束日期
        
        Returns:
            DataFrame with quality factors
        """
        results = []
        
        # 取得所有交易日
        trading_dates = self.db.stock_price.distinct('date', {
            'date': {'$gte': start_date, '$lte': end_date}
        })
        
        for date in sorted(trading_dates):
            for symbol in symbols:
                factors = self.calculate_all_quality_factors(symbol, date)
                results.append(factors)
        
        return pd.DataFrame(results)
