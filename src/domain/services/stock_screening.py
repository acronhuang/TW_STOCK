"""股票篩選 Domain Service — 跨實體的業務邏輯

整合 Valuation + Risk + FinancialHealth 做出投資決策。
不依賴具體 DB（透過 Repository 介面）。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
from ..models.valuation import ValuationResult


@dataclass
class ScreeningCriteria:
    """篩選條件（Value Object）"""
    min_score: float = 72
    max_risk_level: str = '中風險'
    min_upside_pct: float = 5.0
    min_financial_score: float = 65
    pe_range: tuple = (5, 20)
    min_sharpe: float = -0.6


@dataclass
class ScreeningResult:
    """篩選結果"""
    symbol: str
    name: str
    price: float
    total_score: float
    pe: Optional[float]
    upside_pct: float
    sharpe: float
    risk_level: str
    dividend_yield: float
    financial_grade: str
    tier: str  # 'strong_buy' | 'buy' | 'consider'

    @property
    def is_strong_buy(self) -> bool:
        return self.sharpe > 0.5 and self.upside_pct > 20

    @property
    def is_buy(self) -> bool:
        return self.sharpe > 0 and self.upside_pct > 15


def classify_tier(sharpe: float, upside: float) -> str:
    """分級：強烈推薦 / 推薦 / 可考慮"""
    if sharpe > 0.5 and upside > 20:
        return 'strong_buy'
    elif sharpe > 0 and upside > 15:
        return 'buy'
    else:
        return 'consider'


def apply_pku_rules(cost: float, current: float, ma60: Optional[float],
                    ma_trend: str) -> str:
    """北大法則判斷（純業務邏輯，不含 DB 查詢）

    Returns: '持有' | '止損出場' | '減碼觀察' | '留意趨勢'
    """
    pnl_pct = (current - cost) / cost * 100 if cost > 0 else 0
    below_ma60 = current < ma60 if ma60 else None

    if pnl_pct < -5 and below_ma60:
        return '止損出場'
    elif pnl_pct < -5:
        return '止損出場'
    elif below_ma60 and pnl_pct < -3:
        return '減碼觀察'
    elif below_ma60 and pnl_pct >= 0:
        return '留意趨勢'
    elif ma_trend == '空頭排列' and pnl_pct < -3:
        return '減碼觀察'
    elif ma_trend == '空頭排列':
        return '留意趨勢'
    else:
        return '持有'
