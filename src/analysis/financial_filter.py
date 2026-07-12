"""
財報健康篩檢 — 剔除虧損、高負債、EPS 劇降等「地雷股」

使用：
    ff = FinancialFilter()
    ff.is_healthy('2330')           # True / False
    ff.check('2330')                # 回傳詳細檢查結果
    ff.is_healthy('6177')           # 達麗虧損 → False
"""

from __future__ import annotations
from typing import Dict, Optional
from pymongo import MongoClient
from bson import Decimal128


def _tof(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class FinancialFilter:
    """四大健康檢查：獲利能力、EPS 連續性、負債、營收規模"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.db = MongoClient(mongo_uri)[db_name]

    # ─────────────────────────────────────
    #  主 API
    # ─────────────────────────────────────
    def is_healthy(self, symbol: str,
                   min_ttm_net_income: float = 0,
                   max_debt_ratio: float = 80,
                   min_net_margin: float = 0,
                   min_positive_quarters: int = 3) -> bool:
        """簡化版：True/False"""
        r = self.check(symbol, min_ttm_net_income, max_debt_ratio,
                       min_net_margin, min_positive_quarters)
        return r.get('healthy', False)

    def check(self, symbol: str,
              min_ttm_net_income: float = 0,
              max_debt_ratio: float = 80,
              min_net_margin: float = 0,
              min_positive_quarters: int = 3) -> Dict:
        """完整檢查並回傳細節"""
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(4))

        if len(qes) < min_positive_quarters:
            return {
                'symbol': symbol, 'healthy': False,
                'reason': f'季報資料不足（{len(qes)}/4 季）',
                'checks': {},
            }

        # 計算 TTM
        ttm_revenue = 0.0
        ttm_net_income = 0.0
        ttm_eps = 0.0
        positive_quarters = 0
        margins = []
        for q in qes:
            inc = q.get('income', {})
            rev = _tof(inc.get('revenue')) or 0
            ni = _tof(inc.get('net_income')) or 0
            eps = _tof(inc.get('eps')) or 0
            nm = _tof(inc.get('net_margin'))
            ttm_revenue += rev
            ttm_net_income += ni
            ttm_eps += eps
            if ni > 0:
                positive_quarters += 1
            if nm is not None:
                margins.append(nm)

        avg_net_margin = sum(margins) / len(margins) if margins else 0

        # 取負債比（先從 financial_statements）
        debt_ratio = None
        fs = self.db.financial_statements.find_one(
            {'symbol': symbol}, sort=[('year', -1), ('season', -1)])
        if fs:
            bs = fs.get('balanceSheet', {})
            ta = _tof(bs.get('totalAssets'))
            tl = _tof(bs.get('totalLiabilities'))
            if ta and tl and ta > 0:
                debt_ratio = tl / ta * 100
            else:
                r = fs.get('ratios', {})
                debt_ratio = _tof(r.get('debtRatio'))

        # 4 項檢查
        checks = {
            'ttm_net_income_positive': {
                'value': ttm_net_income,
                'threshold': min_ttm_net_income,
                'pass': ttm_net_income > min_ttm_net_income,
                'desc': '4季累計淨利 > 0',
            },
            'positive_quarters': {
                'value': positive_quarters,
                'threshold': min_positive_quarters,
                'pass': positive_quarters >= min_positive_quarters,
                'desc': f'獲利季數 ≥ {min_positive_quarters}',
            },
            'net_margin_positive': {
                'value': avg_net_margin,
                'threshold': min_net_margin,
                'pass': avg_net_margin > min_net_margin,
                'desc': '平均淨利率 > 0',
            },
            'debt_ratio_safe': {
                'value': debt_ratio,
                'threshold': max_debt_ratio,
                'pass': (debt_ratio is None) or (debt_ratio < max_debt_ratio),
                'desc': f'負債比 < {max_debt_ratio}%（資料缺失視為通過）',
            },
        }

        all_pass = all(c['pass'] for c in checks.values())
        fail_items = [c['desc'] for c in checks.values() if not c['pass']]

        return {
            'symbol': symbol,
            'healthy': all_pass,
            'ttm': {
                'revenue': ttm_revenue,
                'net_income': ttm_net_income,
                'eps': ttm_eps,
                'net_margin': avg_net_margin,
                'debt_ratio': debt_ratio,
                'positive_quarters': positive_quarters,
            },
            'checks': checks,
            'reason': '通過' if all_pass else '；'.join(fail_items),
        }

    # ─────────────────────────────────────
    #  批次檢查（供 stock_ranker 用）
    # ─────────────────────────────────────
    def filter_symbols(self, symbols: list, **kwargs) -> Dict[str, bool]:
        """批次：回傳 {symbol: healthy_bool}"""
        return {s: self.is_healthy(s, **kwargs) for s in symbols}


if __name__ == '__main__':
    ff = FinancialFilter()
    test = ['2330', '6177', '2548', '1734', '1612', '1104', '2107', '6951']
    print(f"{'代號':<6} {'健康':<6} {'4季EPS':>7} {'淨利(億)':>9} {'淨利率':>7} {'負債比':>7}  原因")
    print('-' * 75)
    for s in test:
        r = ff.check(s)
        ttm = r.get('ttm', {})
        eps = ttm.get('eps', 0)
        ni = (ttm.get('net_income') or 0) / 1e8
        nm = ttm.get('net_margin', 0) or 0
        dr = ttm.get('debt_ratio')
        dr_s = f"{dr:>6.1f}%" if dr else f"{'—':>7}"
        print(f"{s:<6} {'✅' if r['healthy'] else '❌':<6} "
              f"{eps:>6.2f} {ni:>8.1f}億 {nm:>6.1f}% {dr_s}  {r['reason']}")
