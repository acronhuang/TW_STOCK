"""
謝富旭研究分析法（從實際文章提煉的分析框架）
========================================
不只追蹤清單，把老師的「思考方式」變成可執行的分析模組。

核心分析方法：
  1. 財報驚喜偵測：Q 營收成長 vs 股價是否已反映
  2. EPS → 配息 → 合理價 推演鏈
  3. 配股效應分析：獲利成長能否追上股本膨脹
  4. 填息條件評估：今年 EPS ≥ 去年 → 填息機率高
  5. 結構性成長辨識：以前沒有但現在很多的收入
  6. 三段式風控：大盤跌幅 → 部位調整
"""

from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import Decimal128
import numpy as np
import os
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)


def _tof(v) -> Optional[float]:
    if isinstance(v, Decimal128): return float(v.to_decimal())
    try: return float(v)
    except: return None


class HsiehAnalysis:
    """謝富旭研究分析法"""

    def __init__(self, mongo_uri: str = None, db_name: str = "tw_stock_analysis"):
        uri = mongo_uri or os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.db = MongoClient(uri)[db_name]

    def full_research(self, symbol: str) -> Dict:
        """對單支股票做謝富旭式完整研究"""
        p = self.db.stock_price.find_one({'symbol': symbol}, sort=[('date', -1)])
        if not p:
            return {'symbol': symbol, 'error': '無資料'}
        price = _tof(p['close'])
        name = p.get('name', '')

        result = {
            'symbol': symbol, 'name': name, 'price': price,
            'date': datetime.now().strftime('%Y-%m-%d'),
        }

        result['earnings_surprise'] = self.detect_earnings_surprise(symbol, price)
        result['eps_chain'] = self.eps_to_fair_price(symbol)
        result['stock_dividend_effect'] = self.analyze_stock_dividend(symbol)
        result['fill_dividend'] = self.assess_fill_dividend(symbol)
        result['structural_growth'] = self.detect_structural_growth(symbol)
        result['market_risk'] = self.three_stage_risk()

        # 停損三原則檢查（第787期）
        result['stop_loss_check'] = self.check_stop_loss_rules(symbol, price)

        # 綜合評語
        result['verdict'] = self._generate_verdict(result)

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  1. 財報驚喜偵測
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def detect_earnings_surprise(self, symbol: str, price: float) -> Dict:
        """
        財報驚喜 = 營收大幅成長 + 股價尚未反映

        老師原則：不是營收成長越高越好，要看股價是否已經 price in
        例：健鼎 Q1 營收 +22.4% 但股價已漲 44.7% → 不追
            新產 Q1 營收 +10% 但股價沒反映 → 套利空間大
        """
        # 最新月營收 YoY
        rev = self.db.monthly_revenue.find_one(
            {'symbol': symbol, 'yoy_growth': {'$ne': None}},
            sort=[('year_month', -1)])
        rev_yoy = rev.get('yoy_growth', 0) if rev else 0

        # 累計營收 YoY（近 3 月平均）
        revs = list(self.db.monthly_revenue.find(
            {'symbol': symbol, 'yoy_growth': {'$ne': None}}
        ).sort('year_month', -1).limit(3))
        avg_rev_yoy = np.mean([r.get('yoy_growth', 0) for r in revs]) if revs else 0

        # 股價近 3 月漲幅
        prices = list(self.db.stock_price.find(
            {'symbol': symbol}, {'close': 1}
        ).sort('date', -1).limit(60))
        closes = [_tof(p['close']) for p in prices if _tof(p.get('close'))]
        price_3m_change = ((closes[0] - closes[-1]) / closes[-1] * 100) if len(closes) >= 40 else 0

        # 判定：營收成長 > 股價漲幅 = 有驚喜空間
        gap = avg_rev_yoy - price_3m_change
        if avg_rev_yoy > 5 and gap > 5:
            verdict = '🟢 有驚喜空間（營收成長未反映在股價）'
            score = min(gap / 5, 5)
        elif avg_rev_yoy > 0 and gap > 0:
            verdict = '🟡 小幅驚喜空間'
            score = 2
        elif price_3m_change > avg_rev_yoy + 10:
            verdict = '🔴 股價已超前反映（追高危險）'
            score = -3
        else:
            verdict = '⚪ 無明顯驚喜'
            score = 0

        return {
            'rev_yoy': round(rev_yoy, 1),
            'avg_rev_yoy_3m': round(avg_rev_yoy, 1),
            'price_3m_change': round(price_3m_change, 1),
            'gap': round(gap, 1),
            'verdict': verdict,
            'score': round(score, 1),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  2. EPS → 配息 → 合理價 推演鏈
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def eps_to_fair_price(self, symbol: str) -> Dict:
        """
        老師估價法：
          預估全年 EPS → 乘配息率 → 得預估配息 → 除以期望殖利率 → 合理價
          合理價 = (EPS × 配息率) ÷ 期望殖利率
        """
        # 近 4 季 EPS（TTM）
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(qes) < 4:
            return {'error': '季報不足'}

        ttm_eps = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[:4])
        prev_eps = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[4:8]) if len(qes) >= 8 else ttm_eps

        # 配息率推估（從歷史股利 / EPS）
        divs = list(self.db.dividend_detail.find(
            {'stock_id': symbol, 'cash_earnings_distribution': {'$gt': 0}}
        ).sort('date', -1).limit(3))
        avg_div = np.mean([_tof(d.get('cash_earnings_distribution', 0)) or 0 for d in divs]) if divs else 0
        payout_ratio = (avg_div / prev_eps * 100) if prev_eps > 0 else 60

        # 預估未來配息
        est_div = ttm_eps * min(payout_ratio, 80) / 100

        # 合理價區間
        fair_low = est_div / 0.08 if est_div > 0 else None   # 8% 殖利率
        fair_high = est_div / 0.065 if est_div > 0 else None  # 6.5%

        # EPS 成長趨勢
        eps_growth = ((ttm_eps - prev_eps) / prev_eps * 100) if prev_eps > 0 else 0

        return {
            'ttm_eps': round(ttm_eps, 2),
            'prev_eps': round(prev_eps, 2),
            'eps_growth': round(eps_growth, 1),
            'payout_ratio': round(payout_ratio, 1),
            'est_dividend': round(est_div, 2),
            'fair_price_low': round(fair_low, 1) if fair_low else None,
            'fair_price_high': round(fair_high, 1) if fair_high else None,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  3. 配股效應分析
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def analyze_stock_dividend(self, symbol: str) -> Dict:
        """
        老師原則：配股好不好取決於是否為成長股
        如果獲利成長能追上股本膨脹 → 支持配股
        否則 → 反對（股本過度膨脹）
        """
        latest_div = self.db.dividend_detail.find_one(
            {'stock_id': symbol}, sort=[('date', -1)])
        if not latest_div:
            return {'has_stock_dividend': False}

        stock_div = _tof(latest_div.get('stock_earnings_distribution', 0)) or 0
        cash_div = _tof(latest_div.get('cash_earnings_distribution', 0)) or 0

        if stock_div <= 0:
            return {'has_stock_dividend': False, 'cash_div': cash_div}

        # 股本膨脹率 = 股票股利 / 面額10 × 100%
        dilution_pct = stock_div / 10 * 100

        # EPS 需要成長多少才能不被稀釋
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(4))
        ttm_eps = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[:4])

        required_growth = dilution_pct  # 獲利成長率需 ≥ 股本膨脹率

        return {
            'has_stock_dividend': True,
            'stock_div': stock_div,
            'cash_div': cash_div,
            'dilution_pct': round(dilution_pct, 1),
            'required_growth': round(required_growth, 1),
            'ttm_eps': round(ttm_eps, 2),
            'verdict': f"獲利需成長 {required_growth:.1f}% 才能追上股本膨脹" if stock_div > 0 else '',
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  4. 填息條件評估
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def assess_fill_dividend(self, symbol: str) -> Dict:
        """
        老師原則：今年 EPS ≥ 去年 EPS → 填息機率高
        即使今年無法填息，只要 EPS 成長，明後年也會填
        """
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(qes) < 4:
            return {'verdict': '資料不足'}

        ttm_eps = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[:4])
        prev_eps = sum(_tof(q.get('income', {}).get('eps')) or 0 for q in qes[4:8]) if len(qes) >= 8 else None

        if prev_eps and prev_eps > 0:
            eps_vs_prev = ttm_eps / prev_eps
            if eps_vs_prev >= 1.0:
                verdict = '🟢 填息條件佳（今年EPS ≥ 去年）'
                probability = '高'
            elif eps_vs_prev >= 0.9:
                verdict = '🟡 填息機率中等（EPS 小幅衰退）'
                probability = '中'
            else:
                verdict = '🔴 填息困難（EPS 大幅衰退）'
                probability = '低'
        else:
            verdict = '⚪ 無法判斷'
            probability = '未知'

        return {
            'ttm_eps': round(ttm_eps, 2),
            'prev_eps': round(prev_eps, 2) if prev_eps else None,
            'eps_ratio': round(eps_vs_prev, 2) if prev_eps else None,
            'fill_probability': probability,
            'verdict': verdict,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  5. 結構性成長辨識
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def detect_structural_growth(self, symbol: str) -> Dict:
        """
        老師定義：
        結構性成長 = 以前沒有或不多，但現在很多的獲利
        持續性成長 = 趨勢向上（如台股成交量持續放大）
        至少成長達 3 年才算成長股
        """
        qes = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}
        ).sort([('year', -1), ('season', -1)]).limit(12))

        if len(qes) < 8:
            return {'is_growth': False, 'reason': '歷史資料不足'}

        # 按年加總 EPS
        by_year = {}
        for q in qes:
            y = q.get('year')
            eps = _tof(q.get('income', {}).get('eps')) or 0
            if y not in by_year:
                by_year[y] = 0
            by_year[y] += eps

        years = sorted(by_year.keys(), reverse=True)
        if len(years) < 3:
            return {'is_growth': False, 'reason': '不足3年'}

        # 連續成長幾年
        growth_years = 0
        for i in range(len(years) - 1):
            if by_year[years[i]] > by_year[years[i + 1]]:
                growth_years += 1
            else:
                break

        # CAGR
        if len(years) >= 3 and by_year[years[-1]] > 0:
            n = len(years) - 1
            cagr = ((by_year[years[0]] / by_year[years[-1]]) ** (1 / n) - 1) * 100
        else:
            cagr = 0

        is_growth = growth_years >= 2 and cagr > 5

        return {
            'is_growth': is_growth,
            'growth_years': growth_years,
            'eps_cagr': round(cagr, 1),
            'eps_by_year': {str(y): round(by_year[y], 2) for y in years[:4]},
            'verdict': f"📈 成長股（連續{growth_years}年成長，CAGR {cagr:.1f}%）" if is_growth else '➡️ 非成長股',
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  6. 三段式風控
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def three_stage_risk(self) -> Dict:
        """大盤從年內高點跌落幅度 → 部位調整"""
        prices = list(self.db.stock_price.find(
            {'symbol': '0050'}, {'close': 1}
        ).sort('date', -1).limit(250))
        closes = [_tof(p['close']) for p in prices if _tof(p.get('close'))]
        if not closes:
            return {'level': '未知'}

        high = max(closes)
        current = closes[0]
        drop = (current - high) / high * 100

        if drop > -7:
            return {'level': '正常', 'drop': round(drop, 1), 'action': '正常操作', 'reduce': 0}
        elif drop > -10:
            return {'level': '警示', 'drop': round(drop, 1), 'action': '減碼10%', 'reduce': 10}
        else:
            return {'level': '修正', 'drop': round(drop, 1), 'action': '減碼20%，準備撿便宜', 'reduce': 20}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  綜合評語
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def check_stop_loss_rules(self, symbol: str, price: float) -> Dict:
        """
        謝富旭停損三原則（第787期 2026/4/24）
        1. 扛不住：持股比重太高
        2. 判斷錯誤：EPS不如預期
        3. 等價轉移：有更好標的
        """
        checks = []

        # 原則一：持股集中度風控（需外部傳入）
        checks.append({
            'rule': '原則一：扛不住',
            'desc': '單一持股不超過20%，跌20%損失不超過總部位5%',
            'action': '若持股比重過高，減碼至可承受範圍',
        })

        # 原則二：EPS 判斷錯誤
        chain = self.eps_to_fair_price(symbol)
        eps_growth = chain.get('eps_growth', 0)
        if eps_growth < -20:
            checks.append({
                'rule': '原則二：判斷錯誤',
                'desc': f'EPS YoY {eps_growth:+.1f}%（大幅衰退）',
                'action': '⚠️ 考慮認錯停損',
                'triggered': True,
            })
        else:
            checks.append({
                'rule': '原則二：判斷錯誤',
                'desc': f'EPS YoY {eps_growth:+.1f}%',
                'action': '✅ EPS 未大幅偏離',
                'triggered': False,
            })

        # 原則三：等價轉移（標記但需人工判斷）
        checks.append({
            'rule': '原則三：等價轉移',
            'desc': '獲利OK但股價不給力時，找殖利率更高+動能更強的替代',
            'action': '比較同類標的殖利率，若有更好選擇可轉移',
        })

        return {'checks': checks}

    def _generate_verdict(self, r: Dict) -> str:
        points = []
        surprise = r.get('earnings_surprise', {})
        if surprise.get('score', 0) > 3:
            points.append('財報有驚喜空間')
        if surprise.get('score', 0) < -1:
            points.append('股價已超前反映')

        chain = r.get('eps_chain', {})
        if chain.get('eps_growth', 0) > 10:
            points.append(f"EPS成長{chain['eps_growth']:.0f}%")

        growth = r.get('structural_growth', {})
        if growth.get('is_growth'):
            points.append(f"成長股（CAGR {growth['eps_cagr']:.0f}%）")

        fill = r.get('fill_dividend', {})
        if fill.get('fill_probability') == '高':
            points.append('填息條件佳')

        stock_div = r.get('stock_dividend_effect', {})
        if stock_div.get('has_stock_dividend'):
            points.append(f"配股（需成長{stock_div['required_growth']:.0f}%追上）")

        if not points:
            return '⚪ 無特別訊號'
        return '｜'.join(points)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from dotenv import load_dotenv
    load_dotenv()

    ha = HsiehAnalysis()

    for sym, name in [('2850', '新產'), ('6005', '群益證'), ('9911', '櫻花'), ('2330', '台積電')]:
        r = ha.full_research(sym)
        print(f"\n{'━'*60}")
        print(f"  📕 {sym} {name} — 謝富旭研究分析")
        print(f"{'━'*60}")
        print(f"  現價: {r['price']}")

        s = r.get('earnings_surprise', {})
        print(f"\n  ①財報驚喜: {s.get('verdict','')}")
        print(f"    營收YoY {s.get('avg_rev_yoy_3m',0):+.1f}% vs 股價3M {s.get('price_3m_change',0):+.1f}%  差距 {s.get('gap',0):+.1f}%")

        c = r.get('eps_chain', {})
        if 'error' not in c:
            print(f"\n  ②EPS推演: TTM {c.get('ttm_eps',0):.2f} (YoY {c.get('eps_growth',0):+.1f}%)")
            print(f"    配息率 {c.get('payout_ratio',0):.0f}% → 預估配息 {c.get('est_dividend',0):.2f}")
            if c.get('fair_price_low'):
                print(f"    合理價 {c['fair_price_low']:.0f}~{c['fair_price_high']:.0f}")

        g = r.get('structural_growth', {})
        print(f"\n  ③成長性: {g.get('verdict','')}")

        f = r.get('fill_dividend', {})
        print(f"  ④填息: {f.get('verdict','')}")

        d = r.get('stock_dividend_effect', {})
        if d.get('has_stock_dividend'):
            print(f"  ⑤配股: 股票{d['stock_div']}元 → {d['verdict']}")

        print(f"\n  💡 {r.get('verdict','')}")
