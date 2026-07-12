"""Valuation 領域值物件"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ValuationResult:
    """估值結果（Value Object）"""
    symbol: str
    current_price: float
    dcf_fair_value: Optional[float] = None
    ddm_fair_value: Optional[float] = None
    pe_band_fair_value: Optional[float] = None
    composite_fair_value: Optional[float] = None
    upside_pct: Optional[float] = None
    verdict: str = ''
    warnings: List[str] = field(default_factory=list)

    @property
    def is_undervalued(self) -> bool:
        return self.upside_pct is not None and self.upside_pct > 10

    @property
    def is_overvalued(self) -> bool:
        return self.upside_pct is not None and self.upside_pct < -10
