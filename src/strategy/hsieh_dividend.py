"""
謝富旭深度價值存股法（修正版）
========================================
參考《今周刊》存股助理電子報總監 謝富旭 選股體系

核心精神：像經營生意一樣投資，強調穩定現金流與安全邊際

一、深度價值篩選（3 大策略）
  1. 本業獲利能力：毛利率衰退幅度 < 營收衰退幅度（議價力）
  2. 抗壓性與成長性：景氣冷衰退少，景氣熱成長多
  3. 穩定配息記錄：長期連續配息

二、安全三門檻
  1. 負債比率 < 60%
  2. 速動比率 > 100%
  3. 未分配盈餘 > 2~3 個股本（家底深厚）

三、估價術：未來配息估算法
  合理買進價 = 未來一年預估配息 ÷ 期望殖利率（7%~8%）

四、三段式風控
  加權指數從年內高點下跌 7% → 減碼 10%
  下跌 10% → 再減碼 10%（共 -20%）
  永遠保留 2 年生活準備金

五、資產配置
  高股息 ETF ≤ 30%，其餘配成長股
"""

from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import Decimal128
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


def _tof(v) -> Optional[float]:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class HsiehDividendStrategy:
    """謝富旭深度價值存股法"""

    # 安全三門檻
    MAX_DEBT_RATIO = 60       # 負債比 < 60%
    MIN_QUICK_RATIO = 100     # 速動比 > 100%
    MIN_RETAINED_RATIO = 2.0  # 未分配盈餘 > 2 個股本

    # 估價
    TARGET_YIELD_LOW = 7.0    # 期望殖利率下限 %
    TARGET_YIELD_HIGH = 8.0   # 期望殖利率上限 %

    # 配息
    MIN_CONSECUTIVE_YEARS = 5  # 連續配息年數

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.db = MongoClient(mongo_uri)[db_name]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  主掃描
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def scan(self, limit: int = 30) -> List[Dict]:
        """全市場掃描"""
        logger.info("開始謝富旭深度價值掃描...")

        # 取有殖利率 > 4% 的股票（先粗篩）
        candidates = list(self.db.stock_factors.aggregate([
            {'$match': {'dividend_yield': {'$gt': 4}}},
            {'$sort': {'date': -1}},
            {'$group': {
                '_id': '$symbol',
                'dividend_yield': {'$first': '$dividend_yield'},
                'pb_ratio': {'$first': '$pb_ratio'},
                'pe_ratio': {'$first': '$pe_ratio'},
            }},
        ]))
        logger.info(f"  粗篩殖利率 > 4%: {len(candidates)} 支")

        results = []
        for c in candidates:
            sym = c['_id']
            detail = self._evaluate(sym)
            if detail and detail['total_score'] >= 50:
                results.append(detail)

        results.sort(key=lambda x: -x['total_score'])
        logger.info(f"  通過篩選: {len(results)} 支")
        return results[:limit]

    def _evaluate(self, symbol: str) -> Optional[Dict]:
        """對單支股票做謝富旭全面評估"""
        price_doc = self.db.stock_price.find_one(
            {'symbol': symbol}, sort=[('date', -1)])
        if not price_doc:
            return None
        price = _tof(price_doc.get('close'))
        name = price_doc.get('name', '')
        if not price or price <= 0:
            return None

        scores = {}
        checks = {}

        # ━━━ 一、本業獲利能力（25 分）━━━
        profitability = self._check_profitability(symbol)
        scores['profitability'] = profitability['score']
        checks['profitability'] = profitability

        # ━━━ 二、安全三門檻（25 分）━━━
        safety = self._check_safety_thresholds(symbol)
        scores['safety'] = safety['score']
        checks['safety'] = safety

        # ━━━ 三、配息穩定性（20 分）━━━
        dividend = self._check_dividend_stability(symbol, price)
        scores['dividend'] = dividend['score']
        checks['dividend'] = dividend

        # ━━━ 四、估價（合理買進價）（20 分）━━━
        valuation = self._check_valuation(symbol, price, dividend)
        scores['valuation'] = valuation['score']
        checks['valuation'] = valuation

        # ━━━ 五、抗壓性加分（10 分）━━━
        resilience = self._check_resilience(symbol)
        scores['resilience'] = resilience['score']
        checks['resilience'] = resilience

        total = sum(scores.values())

        # 安全門檻未過 → 扣分（但不歸零）
        if not safety.get('all_pass', False):
            total = max(total - 10, 0)

        # 即將除息追蹤
        ex_div = self._check_upcoming_ex_dividend(symbol)

        # EPS 趨勢（3 年）
        eps_trend = self._eps_trend(symbol)

        return {
            'symbol': symbol,
            'name': name,
            'price': price,
            'total_score': round(total, 1),
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'checks': checks,
            'zone': valuation.get('zone', ''),
            'zones': valuation.get('zones', {}),
            'estimated_dividend': valuation.get('estimated_dividend'),
            'fair_price_low': valuation.get('fair_price_low'),
            'fair_price_high': valuation.get('fair_price_high'),
            'dividend_yield': round(dividend.get('current_yield', 0), 2),
            'consecutive_years': dividend.get('consecutive_years', 0),
            'avg_dividend': round(dividend.get('avg_dividend', 0), 2),
            'growing': dividend.get('growing', False),
            'debt_ratio': safety.get('debt_ratio'),
            'quick_ratio': safety.get('quick_ratio'),
            'retained_ratio': safety.get('retained_ratio'),
            'gross_margin': profitability.get('gross_margin'),
            'operating_margin': profitability.get('operating_margin'),
            'safety_pass': safety.get('all_pass', False),
            'upcoming_ex_div': ex_div,
            'eps_trend': eps_trend,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  一、本業獲利能力
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_profitability(self, symbol: str) -> Dict:
        """毛利率穩定 + 營業利益率 + 議價能力"""
        score = 0
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(qes) < 4:
            return {'score': 5, 'gross_margin': None, 'operating_margin': None}

        # 近 4 季平均
        gms = [_tof(q.get('income', {}).get('gross_margin')) for q in qes[:4]]
        oms = [_tof(q.get('income', {}).get('operating_margin')) for q in qes[:4]]
        gms = [g for g in gms if g is not None]
        oms = [o for o in oms if o is not None]

        gm = np.mean(gms) if gms else None
        om = np.mean(oms) if oms else None

        # 毛利率 > 20% → 10 分
        if gm and gm > 30:
            score += 12
        elif gm and gm > 20:
            score += 10
        elif gm and gm > 10:
            score += 6

        # 營業利益率 > 10% → 8 分
        if om and om > 15:
            score += 8
        elif om and om > 10:
            score += 6
        elif om and om > 5:
            score += 4

        # 議價力：毛利率衰退幅度 < 營收衰退幅度 → 5 分
        if len(qes) >= 8:
            gms_prev = [_tof(q.get('income', {}).get('gross_margin')) for q in qes[4:8]]
            gms_prev = [g for g in gms_prev if g is not None]
            revs_now = [_tof(q.get('income', {}).get('revenue')) or 0 for q in qes[:4]]
            revs_prev = [_tof(q.get('income', {}).get('revenue')) or 0 for q in qes[4:8]]

            if gms and gms_prev and sum(revs_prev) > 0:
                gm_change = (np.mean(gms) - np.mean(gms_prev)) / np.mean(gms_prev) * 100
                rev_change = (sum(revs_now) - sum(revs_prev)) / sum(revs_prev) * 100
                # 毛利率衰退 < 營收衰退 = 有議價力
                if rev_change < 0 and gm_change > rev_change:
                    score += 5

        return {
            'score': min(score, 25),
            'gross_margin': round(gm, 1) if gm else None,
            'operating_margin': round(om, 1) if om else None,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  二、安全三門檻
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_safety_thresholds(self, symbol: str) -> Dict:
        """負債比 < 60% / 速動比 > 100% / 未分配盈餘 > 2 個股本"""
        score = 0
        debt_ratio = None
        quick_ratio = None
        retained_ratio = None
        pass_count = 0

        fs = self.db.financial_statements.find_one(
            {'symbol': symbol}, sort=[('year', -1), ('season', -1)])

        if fs:
            bs = fs.get('balanceSheet', {})
            ta = _tof(bs.get('totalAssets'))
            tl = _tof(bs.get('totalLiabilities'))
            ca = _tof(bs.get('currentAssets'))
            cl = _tof(bs.get('currentLiabilities'))
            inv = _tof(bs.get('inventory') or bs.get('inventories'))
            eq = _tof(bs.get('totalEquity') or bs.get('equity'))
            retained = _tof(bs.get('retainedEarnings') or bs.get('retained_earnings'))

            # 門檻 1: 負債比
            if ta and tl and ta > 0:
                debt_ratio = tl / ta * 100
                if debt_ratio < self.MAX_DEBT_RATIO:
                    score += 8
                    pass_count += 1

            # 門檻 2: 速動比
            if ca and cl and cl > 0:
                inv_val = inv or 0
                quick_ratio = (ca - inv_val) / cl * 100
                if quick_ratio > self.MIN_QUICK_RATIO:
                    score += 8
                    pass_count += 1

            # 門檻 3: 未分配盈餘 > 2 個股本
            if retained and eq and eq > 0:
                retained_ratio = retained / eq
                if retained_ratio > self.MIN_RETAINED_RATIO:
                    score += 9
                    pass_count += 1
        else:
            # 沒有 financial_statements，從 stock_factors 推算
            f = self.db.stock_factors.find_one({'symbol': symbol}, sort=[('date', -1)])
            if f:
                pb = _tof(f.get('pb_ratio'))
                pe = _tof(f.get('pe_ratio'))
                if pb and pe and pe > 0:
                    # ROE = PB/PE，若 ROE > 8% 且 PB < 2 → 基本通過
                    roe = pb / pe * 100
                    if roe > 8 and pb < 2:
                        score = 15
                        pass_count = 2
                    elif pb < 2:
                        score = 10
                        pass_count = 1
                    else:
                        score = 5
                        pass_count = 0
                else:
                    score = 8
                    pass_count = 1
            else:
                score = 8
                pass_count = 1

        return {
            'score': min(score, 25),
            'debt_ratio': round(debt_ratio, 1) if debt_ratio is not None else None,
            'quick_ratio': round(quick_ratio, 1) if quick_ratio is not None else None,
            'retained_ratio': round(retained_ratio, 2) if retained_ratio is not None else None,
            'all_pass': pass_count >= 2,  # 至少 2/3 門檻通過
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  三、配息穩定性
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_dividend_stability(self, symbol: str, price: float) -> Dict:
        """連續配息年數 + 平均股利 + 殖利率"""
        score = 0
        divs = list(self.db.dividend_detail.find(
            {'stock_id': symbol}, {'date': 1, 'cash_earnings_distribution': 1}
        ).sort('date', -1).limit(15))

        if not divs:
            return {'score': 0, 'consecutive_years': 0, 'avg_dividend': 0,
                    'current_yield': 0, 'growing': False}

        by_year = {}
        for d in divs:
            year = str(d.get('date', ''))[:4]
            cash = _tof(d.get('cash_earnings_distribution', 0)) or 0
            if year not in by_year:
                by_year[year] = 0
            by_year[year] += cash

        years = sorted(by_year.keys(), reverse=True)
        consecutive = 0
        for y in years:
            if by_year[y] > 0:
                consecutive += 1
            else:
                break

        # 連續配息 → 最高 12 分
        if consecutive >= 10:
            score += 12
        elif consecutive >= 7:
            score += 10
        elif consecutive >= 5:
            score += 8
        elif consecutive >= 3:
            score += 5

        # 殖利率 → 最高 8 分
        avg = sum(by_year[y] for y in years[:3]) / min(len(years), 3) if years else 0
        current_yield = avg / price * 100 if price > 0 else 0
        if current_yield >= 7:
            score += 8
        elif current_yield >= 5:
            score += 6
        elif current_yield >= 3:
            score += 4

        # 成長性
        growing = False
        if len(years) >= 3:
            vals = [by_year[y] for y in years[:3]]
            growing = all(v > 0 for v in vals) and vals[0] >= vals[2]

        return {
            'score': min(score, 20),
            'consecutive_years': consecutive,
            'avg_dividend': avg,
            'current_yield': current_yield,
            'growing': growing,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  四、估價：未來配息估算法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_valuation(self, symbol: str, price: float, div_info: Dict) -> Dict:
        """四區間估價色帶（參考謝富旭 2026/4/13 更新格式）

        紅色=便宜（殖利率 ≥ 8%）  → 積極買進
        綠色=合理（殖利率 6.5-8%）→ 分批佈局
        藍色=殷實（殖利率 5-6.5%）→ 持有不加碼
        紫色=昂貴（殖利率 < 5%）  → 考慮減碼

        估價公式：各區間上下界 = 預估配息 ÷ 殖利率
        """
        # 預估未來配息（用近 3 年趨勢推估，不只看平均）
        est_div = self._estimate_future_dividend(div_info)
        if est_div <= 0:
            return {'score': 5, 'fair_price_low': None, 'fair_price_high': None,
                    'zone': '無法估', 'zones': {}}

        # 四區間
        zones = {
            'cheap':  {'yield_range': '≥8%',     'low': round(est_div / 0.10, 1), 'high': round(est_div / 0.08, 1)},
            'fair':   {'yield_range': '6.5-8%',  'low': round(est_div / 0.08, 1), 'high': round(est_div / 0.065, 1)},
            'solid':  {'yield_range': '5-6.5%',  'low': round(est_div / 0.065, 1), 'high': round(est_div / 0.05, 1)},
            'expensive': {'yield_range': '<5%',  'low': round(est_div / 0.05, 1), 'high': None},
        }

        # 判斷現價所在區間
        if price <= zones['cheap']['high']:
            zone = '🔴 便宜'
            score = 20
        elif price <= zones['fair']['high']:
            zone = '🟢 合理'
            score = 15
        elif price <= zones['solid']['high']:
            zone = '🔵 殷實'
            score = 10
        else:
            zone = '🟣 昂貴'
            score = 3

        return {
            'score': score,
            'zone': zone,
            'estimated_dividend': round(est_div, 2),
            'fair_price_low': zones['cheap']['low'],    # 便宜區下界
            'fair_price_high': zones['cheap']['high'],  # 便宜區上界
            'zones': zones,
        }

    def _estimate_future_dividend(self, div_info: Dict) -> float:
        """預估未來配息（考慮成長趨勢）"""
        avg = div_info.get('avg_dividend', 0)
        if avg <= 0:
            return 0

        # 若股利逐年成長 → 用最新一年 × 1.05（保守成長）
        # 若股利衰退 → 用近 3 年平均
        if div_info.get('growing', False):
            return avg * 1.05  # 成長性調整
        return avg

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  五、抗壓性
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_resilience(self, symbol: str) -> Dict:
        """景氣冷衰退少、景氣熱成長多"""
        score = 0
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(qes) < 4:
            return {'score': 5}

        # 近 4 季 vs 前 4 季 EPS 變化
        eps_now = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[:4])
        eps_prev = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[4:8]) if len(qes) >= 8 else eps_now

        if eps_prev > 0:
            eps_change = (eps_now - eps_prev) / eps_prev * 100
            if eps_change > 10:
                score += 10  # EPS 成長 > 10%
            elif eps_change > 0:
                score += 7
            elif eps_change > -10:
                score += 5   # 衰退 < 10%（抗壓）
        else:
            score += 3

        return {'score': min(score, 10)}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  三段式風控
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _check_upcoming_ex_dividend(self, symbol: str) -> Optional[Dict]:
        """檢查是否即將除息（已公布除息日但尚未除息）"""
        today = datetime.now()
        divs = list(self.db.dividend_detail.find(
            {'stock_id': symbol, 'date': {'$gte': today.strftime('%Y-%m-%d')}},
        ).sort('date', 1).limit(1))

        if divs:
            ex_date = str(divs[0].get('date', ''))[:10]
            cash = _tof(divs[0].get('cash_earnings_distribution', 0)) or 0
            return {'ex_date': ex_date, 'cash': cash, 'upcoming': True}

        # 也查近期的（可能日期格式不同）
        divs2 = list(self.db.dividend_detail.find(
            {'stock_id': symbol}
        ).sort('date', -1).limit(1))
        if divs2:
            ex_date = str(divs2[0].get('date', ''))[:10]
            try:
                ex_dt = datetime.strptime(ex_date, '%Y-%m-%d')
                if ex_dt > today:
                    cash = _tof(divs2[0].get('cash_earnings_distribution', 0)) or 0
                    return {'ex_date': ex_date, 'cash': cash, 'upcoming': True}
            except ValueError:
                pass
        return None

    def _eps_trend(self, symbol: str) -> Dict:
        """3 年 EPS 趨勢"""
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(12))

        if len(qes) < 4:
            return {'trend': '資料不足'}

        # 按年加總
        by_year = {}
        for q in qes:
            y = q.get('year')
            eps = _tof(q.get('income', {}).get('eps')) or 0
            if y not in by_year:
                by_year[y] = 0
            by_year[y] += eps

        years = sorted(by_year.keys(), reverse=True)
        if len(years) < 2:
            return {'trend': '資料不足'}

        eps_list = {y: round(by_year[y], 2) for y in years[:3]}

        # 判斷趨勢
        vals = [by_year[y] for y in years[:3]]
        if len(vals) >= 3 and vals[0] > vals[1] > vals[2]:
            trend = '📈 連續成長'
        elif len(vals) >= 2 and vals[0] > vals[1]:
            trend = '📈 成長'
        elif len(vals) >= 2 and vals[0] < vals[1] * 0.8:
            trend = '📉 大幅衰退'
        elif len(vals) >= 2 and vals[0] < vals[1]:
            trend = '📉 衰退'
        else:
            trend = '➡️ 持平'

        return {'trend': trend, 'eps_by_year': eps_list}

    def market_risk_level(self) -> Dict:
        """三段式風控：觀察大盤從年內高點跌落幅度"""
        prices = list(self.db.stock_price.find(
            {'symbol': '0050'}, {'close': 1, 'date': 1}
        ).sort('date', -1).limit(250))

        if not prices:
            return {'level': 'unknown', 'drop_pct': 0, 'action': '資料不足'}

        closes = [_tof(p['close']) for p in prices if _tof(p.get('close'))]
        if not closes:
            return {'level': 'unknown', 'drop_pct': 0, 'action': '資料不足'}

        high = max(closes)
        current = closes[0]
        drop_pct = (current - high) / high * 100

        if drop_pct > -7:
            return {
                'level': '正常',
                'drop_pct': round(drop_pct, 1),
                'high': round(high, 2),
                'current': round(current, 2),
                'action': '正常持有，依計畫操作',
                'reduce_pct': 0,
            }
        elif drop_pct > -10:
            return {
                'level': '警示期',
                'drop_pct': round(drop_pct, 1),
                'high': round(high, 2),
                'current': round(current, 2),
                'action': '⚠️ 減碼 10%（從年高跌 7%）',
                'reduce_pct': 10,
            }
        else:
            return {
                'level': '修正期',
                'drop_pct': round(drop_pct, 1),
                'high': round(high, 2),
                'current': round(current, 2),
                'action': '🔴 減碼 20%（從年高跌 10%+），準備撿便宜',
                'reduce_pct': 20,
            }


if __name__ == '__main__':
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from dotenv import load_dotenv
    load_dotenv()

    hs = HsiehDividendStrategy()

    # 三段式風控
    risk = hs.market_risk_level()
    print(f"\n  📊 三段式風控: {risk['level']}（從年高 {risk.get('high',0)} 跌 {risk['drop_pct']:+.1f}%）")
    print(f"     {risk['action']}")

    results = hs.scan(limit=20)

    print(f"\n{'═'*90}")
    print(f"  📕 謝富旭深度價值存股法 — Top {len(results)}")
    print(f"{'═'*90}\n")
    print(f"  {'#':>2} {'代號':<6} {'名稱':<10} {'股價':>6} {'殖利':>5} {'連配':>4} {'均息':>5} "
          f"{'合理價':>10} {'負債%':>5} {'速動%':>5} {'毛利%':>5} {'安全':>4} {'總分':>5}")
    print(f"  {'─'*90}")

    for i, r in enumerate(results[:20], 1):
        zone = r.get('zone', '?')[:4]
        fp = f"{r['fair_price_low']:.0f}-{r['fair_price_high']:.0f}" if r.get('fair_price_low') else '  —'
        gm = f"{r['gross_margin']:.0f}" if r.get('gross_margin') is not None else ' —'
        safe = '✅' if r['safety_pass'] else '❌'
        ex = '🟡除息' if r.get('upcoming_ex_div') else ''
        eps_t = r.get('eps_trend', {}).get('trend', '')[:4]
        grow = '📈' if r.get('growing') else '  '
        print(f"  {i:>2} {r['symbol']:<6} {r['name']:<10} {r['price']:>6.1f} "
              f"{r['dividend_yield']:>4.1f}% {r['consecutive_years']:>3}年 "
              f"{zone:<5} {fp:>8} {gm:>4}% {safe} {eps_t} {grow} {r['total_score']:>5.1f} {ex}")
