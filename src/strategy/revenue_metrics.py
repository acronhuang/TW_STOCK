"""
選股共用：營收動能（月營收 + 季營收 YoY）
==========================================
獲利確認的「領先層」與「同期層」：
  • 月營收 YoY：monthly_revenue 最新月(每月10號前公布)，最即時的動能領先指標。
  • 季營收 YoY：quarterly_earnings 最新季 vs 去年同季(同季比，消季節性)。
月營收偶有極端值(基期過低)，沿用全市場 >500% 截斷規則。
供 HsiehValueScreen 存股成長精選等共用。
"""
from typing import Optional

YOY_CLAMP = 500.0    # 月營收 YoY 上限截斷(基期過低的假爆發)


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except (TypeError, ValueError, AttributeError):
        return None


def monthly_rev_yoy(db, symbol: str) -> Optional[float]:
    """回最新月營收 YoY%（截斷 >500%）。無資料回 None。"""
    d = db.monthly_revenue.find_one({'symbol': symbol}, sort=[('year_month', -1)])
    y = (d or {}).get('yoy_growth')
    if y is None:
        return None
    y = float(y)
    return round(min(y, YOY_CLAMP), 1)


def quarterly_rev_yoy(db, symbol: str) -> Optional[float]:
    """回最新季營收 YoY%（最新季 vs 去年同季）。資料不足回 None。"""
    q = db.quarterly_earnings.find_one(
        {'symbol': symbol, 'income.revenue': {'$ne': None}},
        {'income.revenue': 1, 'year': 1, 'season': 1},
        sort=[('year', -1), ('season', -1)])
    if not q:
        return None
    rev = _f((q.get('income') or {}).get('revenue'))
    yq = db.quarterly_earnings.find_one(
        {'symbol': symbol, 'year': q['year'] - 1, 'season': q['season']},
        {'income.revenue': 1})
    rev0 = _f((yq or {}).get('income', {}).get('revenue')) if yq else None
    if not (rev and rev0):
        return None
    return round((rev / rev0 - 1) * 100, 1)
