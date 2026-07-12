#!/usr/bin/env python3
"""
財報健康分析（v2 - 完整重寫）
========================================
改進：
- 從 `quarterly_earnings`（1,963 支）取 TTM 數據，不再只限 financial_statements 的 192 支
- 6 維度評分：獲利 / 成長 / 安全 / 效率 / 品質 / 估值
- 杜邦分析 ROE 拆解
- 10 項地雷警示檢查
- A+/A/B+/B/C+/C/D/F 評級

使用：
    fh = FinancialHealthAnalyzer()
    fh.analyze_stock('2330')
"""

from __future__ import annotations
from typing import Dict, List, Optional
from pymongo import MongoClient
from bson import Decimal128


MONGODB_URI = 'mongodb://localhost:27017/'
DB_NAME = 'tw_stock_analysis'


def _tof(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class FinancialHealthAnalyzer:
    """
    完整財報健檢系統，支援全市場 1,963 支股票。

    評分維度（各 0-100 分）：
        獲利能力 profitability  → 毛利率、營益率、淨利率
        成長性 growth            → 營收 YoY、EPS 趨勢
        財務安全 safety          → 負債比、流動比、利息保障
        營運效率 efficiency      → 資產週轉率、存貨週轉
        品質 quality             → ROE、ROA、杜邦
        估值 value               → PE、PB、殖利率（相對）
    """

    WEIGHTS = {
        'profitability': 0.25,
        'growth':        0.20,
        'safety':        0.20,
        'efficiency':    0.10,
        'quality':       0.15,
        'value':         0.10,
    }

    def __init__(self,
                 mongo_uri: str = MONGODB_URI,
                 db_name: str = DB_NAME):
        self.db = MongoClient(mongo_uri)[db_name]

    # ─────────────────────────────────────────────────
    #  主 API
    # ─────────────────────────────────────────────────
    def analyze_stock(self, symbol: str) -> Dict:
        """單股完整財報分析。"""
        ttm = self._calc_ttm(symbol)
        if ttm is None:
            return {'symbol': symbol, 'error': '季報資料不足'}

        balance = self._latest_balance(symbol)
        factors = self.db.stock_factors.find_one(
            {'symbol': symbol}, sort=[('date', -1)]) or {}
        price = _tof(factors.get('pe_ratio'))  # 為 None 則後續 value 降級

        # 6 維評分
        scores = {
            'profitability': self._score_profitability(ttm),
            'growth':        self._score_growth(ttm),
            'safety':        self._score_safety(ttm, balance),
            'efficiency':    self._score_efficiency(ttm, balance),
            'quality':       self._score_quality(ttm, balance),
            'value':         self._score_value(factors),
        }

        total = sum(scores[k] * w for k, w in self.WEIGHTS.items())
        grade = self._grade(total)
        dupont = self._dupont(ttm, balance)
        warnings = self._warnings(ttm, balance, scores)

        return {
            'symbol': symbol,
            'total_score': round(total, 1),
            'grade': grade,
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'ttm': ttm,
            'balance': balance,
            'dupont': dupont,
            'factors': {
                'pe_ratio': _tof(factors.get('pe_ratio')),
                'pb_ratio': _tof(factors.get('pb_ratio')),
                'dividend_yield': _tof(factors.get('dividend_yield')),
            },
            'warnings': warnings,
        }

    def analyze_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        return {s: self.analyze_stock(s) for s in symbols}

    # ─────────────────────────────────────────────────
    #  TTM（Trailing Twelve Months）計算
    # ─────────────────────────────────────────────────
    def _calc_ttm(self, symbol: str) -> Optional[Dict]:
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(qes) < 3:
            return None

        recent4 = qes[:4]
        previous4 = qes[4:8] if len(qes) >= 8 else None

        def sum_field(quarters, field):
            total = 0.0
            valid = 0
            for q in quarters:
                v = _tof(q.get('income', {}).get(field))
                if v is not None:
                    total += v
                    valid += 1
            return total if valid > 0 else None

        def avg_field(quarters, field):
            vals = [_tof(q.get('income', {}).get(field))
                    for q in quarters]
            vals = [v for v in vals if v is not None]
            return sum(vals) / len(vals) if vals else None

        ttm_rev = sum_field(recent4, 'revenue')
        ttm_oi = sum_field(recent4, 'operating_income')
        ttm_ni = sum_field(recent4, 'net_income')
        ttm_eps = sum_field(recent4, 'eps') or 0

        gross_margin = avg_field(recent4, 'gross_margin')
        operating_margin = avg_field(recent4, 'operating_margin')
        net_margin = avg_field(recent4, 'net_margin')

        # 成長率：TTM vs 前 4 季
        rev_yoy = None
        ni_yoy = None
        eps_yoy = None
        if previous4 and len(previous4) >= 3:
            prev_rev = sum_field(previous4, 'revenue')
            prev_ni = sum_field(previous4, 'net_income')
            prev_eps = sum_field(previous4, 'eps')
            if prev_rev and prev_rev > 0 and ttm_rev:
                rev_yoy = (ttm_rev - prev_rev) / prev_rev * 100
            if prev_ni and prev_ni > 0 and ttm_ni:
                ni_yoy = (ttm_ni - prev_ni) / prev_ni * 100
            if prev_eps and prev_eps > 0 and ttm_eps:
                eps_yoy = (ttm_eps - prev_eps) / prev_eps * 100

        # 獲利季數
        pos_quarters = sum(1 for q in recent4
                           if (_tof(q.get('income', {}).get('net_income')) or 0) > 0)

        return {
            'period': f"{recent4[0].get('year')}Q{recent4[0].get('season')} (TTM)",
            'revenue': ttm_rev,
            'operating_income': ttm_oi,
            'net_income': ttm_ni,
            'eps': ttm_eps,
            'gross_margin': gross_margin,
            'operating_margin': operating_margin,
            'net_margin': net_margin,
            'revenue_yoy': rev_yoy,
            'net_income_yoy': ni_yoy,
            'eps_yoy': eps_yoy,
            'positive_quarters': pos_quarters,
            'quarters_analyzed': len(recent4),
        }

    def _latest_balance(self, symbol: str) -> Dict:
        """取資產負債表（優先 financial_statements，fallback quarterly_earnings.balance）。"""
        fs = self.db.financial_statements.find_one(
            {'symbol': symbol}, sort=[('year', -1), ('season', -1)])
        if fs:
            bs = fs.get('balanceSheet', {})
            if bs:
                return {
                    'total_assets': _tof(bs.get('totalAssets')),
                    'total_liabilities': _tof(bs.get('totalLiabilities')),
                    'equity': _tof(bs.get('totalEquity') or bs.get('equity')),
                    'current_assets': _tof(bs.get('currentAssets')),
                    'current_liabilities': _tof(bs.get('currentLiabilities')),
                    'cash': _tof(bs.get('cashAndCashEquivalents') or bs.get('cash')),
                    'inventory': _tof(bs.get('inventory') or bs.get('inventories')),
                    'source': 'financial_statements',
                }

        qe = self.db.quarterly_earnings.find_one(
            {'symbol': symbol}, sort=[('year', -1), ('season', -1)])
        if qe and qe.get('balance'):
            bal = qe['balance']
            return {
                'total_assets': _tof(bal.get('total_assets')),
                'total_liabilities': _tof(bal.get('total_liabilities')),
                'equity': _tof(bal.get('total_equity')),
                'current_assets': _tof(bal.get('current_assets')),
                'current_liabilities': _tof(bal.get('current_liabilities')),
                'cash': _tof(bal.get('cash')),
                'inventory': _tof(bal.get('inventory')),
                'source': 'quarterly_earnings',
            }
        return {'source': None}

    # ─────────────────────────────────────────────────
    #  6 維評分
    # ─────────────────────────────────────────────────
    def _score_profitability(self, ttm: Dict) -> float:
        scores = []
        nm = ttm.get('net_margin')
        om = ttm.get('operating_margin')
        gm = ttm.get('gross_margin')
        if nm is not None:
            scores.append(self._scale(nm, bad=0, good=20, excellent=40))
        if om is not None:
            scores.append(self._scale(om, bad=0, good=15, excellent=30))
        if gm is not None:
            scores.append(self._scale(gm, bad=10, good=30, excellent=50))
        return sum(scores) / len(scores) if scores else 50

    def _score_growth(self, ttm: Dict) -> float:
        scores = []
        for key in ('revenue_yoy', 'net_income_yoy', 'eps_yoy'):
            v = ttm.get(key)
            if v is not None:
                scores.append(self._scale(v, bad=-20, good=10, excellent=30))
        if not scores:
            return 50
        base = sum(scores) / len(scores)
        if ttm.get('positive_quarters') == 4:
            base = min(100, base + 10)
        return base

    def _score_safety(self, ttm: Dict, balance: Dict) -> float:
        scores = []
        ta = balance.get('total_assets')
        tl = balance.get('total_liabilities')
        if ta and tl and ta > 0:
            debt_ratio = tl / ta * 100
            scores.append(self._scale(debt_ratio, bad=80, good=50, excellent=30,
                                      lower_better=True))

        ca = balance.get('current_assets')
        cl = balance.get('current_liabilities')
        if ca and cl and cl > 0:
            current_ratio = ca / cl
            scores.append(self._scale(current_ratio, bad=1.0, good=1.5, excellent=2.5))

        pq = ttm.get('positive_quarters', 0)
        scores.append(pq / 4 * 100)

        return sum(scores) / len(scores) if scores else 50

    def _score_efficiency(self, ttm: Dict, balance: Dict) -> float:
        rev = ttm.get('revenue')
        ta = balance.get('total_assets')
        if rev and ta and ta > 0:
            turnover = rev / ta
            return self._scale(turnover, bad=0.1, good=0.6, excellent=1.2)
        return 50

    def _score_quality(self, ttm: Dict, balance: Dict) -> float:
        scores = []
        eq = balance.get('equity')
        ta = balance.get('total_assets')
        ni = ttm.get('net_income')

        if ni and eq and eq > 0:
            roe = ni / eq * 100
            scores.append(self._scale(roe, bad=5, good=15, excellent=25))
        if ni and ta and ta > 0:
            roa = ni / ta * 100
            scores.append(self._scale(roa, bad=2, good=6, excellent=12))

        return sum(scores) / len(scores) if scores else 50

    def _score_value(self, factors: Dict) -> float:
        pe = _tof(factors.get('pe_ratio'))
        pb = _tof(factors.get('pb_ratio'))
        dy = _tof(factors.get('dividend_yield'))

        scores = []
        if pe and 0 < pe < 50:
            scores.append(self._scale(pe, bad=30, good=15, excellent=10, lower_better=True))
        if pb and 0 < pb < 10:
            scores.append(self._scale(pb, bad=3, good=1.5, excellent=0.8, lower_better=True))
        if dy is not None and dy > 0:
            scores.append(self._scale(dy, bad=1, good=4, excellent=7))

        return sum(scores) / len(scores) if scores else 50

    # ─────────────────────────────────────────────────
    #  杜邦分析 & 警示
    # ─────────────────────────────────────────────────
    def _dupont(self, ttm: Dict, balance: Dict) -> Dict:
        ni = ttm.get('net_income')
        rev = ttm.get('revenue')
        ta = balance.get('total_assets')
        eq = balance.get('equity')

        nm = (ni / rev * 100) if ni and rev and rev > 0 else None
        turnover = (rev / ta) if rev and ta and ta > 0 else None
        leverage = (ta / eq) if ta and eq and eq > 0 else None
        roe = None
        if nm is not None and turnover is not None and leverage is not None:
            roe = nm / 100 * turnover * leverage * 100
        elif ni and eq and eq > 0:
            roe = ni / eq * 100

        return {
            'net_margin_pct': nm,
            'asset_turnover': turnover,
            'equity_multiplier': leverage,
            'roe_pct': roe,
        }

    def _warnings(self, ttm: Dict, balance: Dict, scores: Dict) -> List[str]:
        out = []
        ni = ttm.get('net_income') or 0
        if ni <= 0:
            out.append(f"4 季累計淨利 {ni/1e8:.1f} 億 (虧損)")
        if ttm.get('positive_quarters', 0) < 3:
            out.append(f"4 季僅 {ttm.get('positive_quarters', 0)} 季獲利")
        nm = ttm.get('net_margin')
        if nm is not None and nm < 0:
            out.append(f"淨利率 {nm:.1f}% (為負)")
        yoy = ttm.get('revenue_yoy')
        if yoy is not None and yoy < -15:
            out.append(f"營收 YoY {yoy:.1f}% (大衰退)")
        eps_yoy = ttm.get('eps_yoy')
        if eps_yoy is not None and eps_yoy < -30:
            out.append(f"EPS YoY {eps_yoy:.1f}% (大幅衰退)")

        ta = balance.get('total_assets')
        tl = balance.get('total_liabilities')
        if ta and tl and ta > 0:
            debt = tl / ta * 100
            if debt > 80:
                out.append(f"負債比 {debt:.1f}% (過高)")

        ca = balance.get('current_assets')
        cl = balance.get('current_liabilities')
        if ca and cl and cl > 0:
            cr = ca / cl
            if cr < 1:
                out.append(f"流動比 {cr:.2f} (流動性不足)")

        if scores['profitability'] < 30:
            out.append("獲利能力偏弱")
        if scores['safety'] < 40:
            out.append("財務安全性偏低")

        return out

    # ─────────────────────────────────────────────────
    #  工具
    # ─────────────────────────────────────────────────
    @staticmethod
    def _scale(v: float, bad: float, good: float, excellent: float,
               lower_better: bool = False) -> float:
        if lower_better:
            if v <= excellent: return 100
            if v <= good:      return 70 + (good - v) / (good - excellent) * 30
            if v <= bad:       return (bad - v) / (bad - good) * 70
            return max(0, 20 - (v - bad))
        else:
            if v >= excellent: return 100
            if v >= good:      return 70 + (v - good) / (excellent - good) * 30
            if v >= bad:       return (v - bad) / (good - bad) * 70
            return max(0, 20 + v - bad) if v > bad - 20 else 0

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 85: return 'A+ 優質'
        if score >= 75: return 'A 良好'
        if score >= 65: return 'B+ 中上'
        if score >= 55: return 'B 普通'
        if score >= 45: return 'C+ 中下'
        if score >= 35: return 'C 偏弱'
        if score >= 25: return 'D 疑慮'
        return 'F 地雷'


def main():
    fh = FinancialHealthAnalyzer()
    tests = ['2330', '2412', '1612', '1104', '2107', '6951', '6177', '2548', '1456', '5522']
    for sym in tests:
        r = fh.analyze_stock(sym)
        if 'error' in r:
            print(f"{sym}: {r['error']}")
            continue
        s = r['scores']
        print(f"\n{sym}  總分 {r['total_score']:>5.1f}  {r['grade']}")
        print(f"  獲利 {s['profitability']:>5.1f}  成長 {s['growth']:>5.1f}  "
              f"安全 {s['safety']:>5.1f}  效率 {s['efficiency']:>5.1f}  "
              f"品質 {s['quality']:>5.1f}  估值 {s['value']:>5.1f}")
        ttm = r['ttm']
        print(f"  TTM: EPS={ttm['eps']:.2f}  淨利率={ttm.get('net_margin') or 0:.1f}%  "
              f"營收YoY={ttm.get('revenue_yoy') or 0:+.1f}%")
        d = r['dupont']
        if d.get('roe_pct'):
            print(f"  杜邦: ROE {d['roe_pct']:.1f}% = 淨利率 {d['net_margin_pct']:.1f}% × "
                  f"週轉 {d['asset_turnover']:.2f} × 槓桿 {d['equity_multiplier']:.2f}")
        if r['warnings']:
            for w in r['warnings'][:3]:
                print(f"  ⚠️  {w}")


if __name__ == '__main__':
    main()
