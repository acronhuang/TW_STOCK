"""
選股共用：TTM EPS + EPS YoY
==========================
以實際財報計算「過去4季 EPS」與「相對去年同期4季的成長率」——
比券商預估更扎實，且能濾出「營收增但獲利縮」的假成長(如承攬/薄利股)。
供 HsiehValueScreen / AganMoatScreen 等共用。

股數採 capital_stock/10(面額10元)，與 stock_factors.pe_ratio 對得起來；
EPS YoY 用「最新4季淨利加總 / 去年同4季淨利加總 - 1」(消除單季季節性)。
"""
from typing import Optional, Tuple


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except (TypeError, ValueError, AttributeError):
        return None


def ttm_eps_yoy(db, symbol: str) -> Tuple[Optional[float], Optional[float]]:
    """回 (TTM_EPS, EPS_YoY%)。資料不足回 (None, None)。"""
    qs = list(db.quarterly_earnings.find(
        {'symbol': symbol}, {'income.net_income': 1, 'balance.capital_stock': 1}
    ).sort([('year', -1), ('season', -1)]).limit(8))
    if len(qs) < 4:
        return None, None
    cs = next((_f((q.get('balance') or {}).get('capital_stock'))
               for q in qs if (q.get('balance') or {}).get('capital_stock')), None)
    if not cs:
        return None, None
    shares = cs / 10.0                      # 面額10元 → 股數

    nis = [_f((q.get('income') or {}).get('net_income')) for q in qs[:4]]
    if any(x is None for x in nis):
        return None, None
    ttm_eps = sum(nis) / shares

    yoy = None
    nis_prev = [_f((q.get('income') or {}).get('net_income')) for q in qs[4:8]]
    if len(nis_prev) == 4 and all(x is not None for x in nis_prev):
        prev = sum(nis_prev)
        if prev > 0:                        # 去年虧轉盈無意義的YoY → 留 None
            yoy = (sum(nis) / prev - 1) * 100
    return round(ttm_eps, 2), (round(yoy, 1) if yoy is not None else None)
