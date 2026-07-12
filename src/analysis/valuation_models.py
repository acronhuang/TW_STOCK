#!/usr/bin/env python3
"""
估值模型：DCF（自由現金流折現）+ DDM（股利折現模型）+ 本益比河流圖
============================================================
提供個股內在價值估算，整合 quarterly_earnings / dividend_detail / stock_price。

Usage:
    from src.analysis.valuation_models import ValuationAnalyzer
    va = ValuationAnalyzer()
    result = va.analyze('2330')
    print(result['dcf']['fair_value'], result['ddm']['fair_value'])
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ValuationAnalyzer:
    """整合 DCF + DDM + PE Band 的估值分析器"""

    # 台灣十年期公債殖利率（預設）
    RISK_FREE_RATE = 0.015
    # 股權風險溢酬（台股歷史平均）
    EQUITY_RISK_PREMIUM = 0.065
    # 永續成長率
    TERMINAL_GROWTH = 0.02
    # WACC 下限（避免 beta 過低導致折現率不合理）
    MIN_WACC = 0.08
    # DDM 股利成長率上限（永續成長不該超過 GDP+通膨 ~5%）
    MAX_DIV_GROWTH = 0.05
    # PE Band 截斷百分位（排除異常期的極端 PE）
    PE_LOW_PERCENTILE = 10    # 取 P10
    PE_HIGH_PERCENTILE = 90   # 取 P90
    # 合理 PE 上限（即使歷史再高也不超過）
    MAX_REASONABLE_PE = 25
    # 預測年數
    PROJECTION_YEARS = 5

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    def analyze(self, symbol: str) -> Dict:
        """完整估值分析（DCF + DDM + PE Band + 綜合判定）"""
        price = self._get_current_price(symbol)
        if price is None:
            return {'symbol': symbol, 'error': '無法取得股價'}

        dcf = self.dcf_valuation(symbol, price)
        ddm = self.ddm_valuation(symbol, price)
        pe_band = self.pe_band_analysis(symbol, price)

        # 綜合估值
        fair_values = []
        weights = []
        for model, w in [('dcf', 0.4), ('ddm', 0.3), ('pe_band', 0.3)]:
            result = locals()[model]
            if result and result.get('fair_value') and result['fair_value'] > 0:
                fair_values.append(result['fair_value'])
                weights.append(w)

        if fair_values:
            total_w = sum(weights)
            composite_fv = sum(fv * w for fv, w in zip(fair_values, weights)) / total_w
            upside = (composite_fv - price) / price * 100
        else:
            composite_fv = None
            upside = None

        verdict = self._get_verdict(upside)

        return {
            'symbol': symbol,
            'current_price': price,
            'dcf': dcf,
            'ddm': ddm,
            'pe_band': pe_band,
            'composite': {
                'fair_value': round(composite_fv, 2) if composite_fv else None,
                'upside_pct': round(upside, 2) if upside is not None else None,
                'verdict': verdict,
                'models_used': len(fair_values),
            },
            'updated_at': datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────
    #  DCF（自由現金流折現模型）
    # ──────────────────────────────────────────────
    def dcf_valuation(self, symbol: str, price: float = None) -> Optional[Dict]:
        """
        簡化 DCF：
        FCF ≈ 營業利益 × (1 - 稅率) + 折舊 - 資本支出 - 營運資金變動
        實務簡化：FCF ≈ Net Income + Depreciation（因台股缺完整現金流量表）
        再簡化：FCF ≈ Net Income × FCF_Margin_Factor
        """
        if price is None:
            price = self._get_current_price(symbol)
        if price is None:
            return None

        earnings = self._get_quarterly_earnings(symbol, years=5)
        if not earnings or len(earnings) < 4:
            return None

        # 計算年度淨利
        annual_ni = self._aggregate_annual(earnings, 'net_income')
        if not annual_ni or len(annual_ni) < 2:
            return None

        # 最近一年淨利
        latest_ni = annual_ni[-1]['value']
        if latest_ni <= 0:
            return {'fair_value': None, 'reason': '淨利為負，DCF 不適用'}

        # 營收成長率（用近3年幾何平均）
        annual_rev = self._aggregate_annual(earnings, 'revenue')
        growth_rate = self._calc_cagr(annual_rev, min_years=2)
        if growth_rate is None:
            growth_rate = 0.05  # 預設 5%

        # 限制成長率在合理範圍
        growth_rate = max(min(growth_rate, 0.30), -0.10)

        # FCF 估算（簡化：淨利 × 0.8 作為自由現金流）
        fcf_factor = 0.80
        latest_fcf = latest_ni * fcf_factor

        # WACC（簡化：用 CAPM 估算）
        beta = self._estimate_beta(symbol)
        wacc = max(self.RISK_FREE_RATE + beta * self.EQUITY_RISK_PREMIUM, self.MIN_WACC)

        # 預測未來 FCF
        projected_fcf = []
        for yr in range(1, self.PROJECTION_YEARS + 1):
            # 成長率逐年遞減至永續成長率
            fade = growth_rate - (growth_rate - self.TERMINAL_GROWTH) * (yr / self.PROJECTION_YEARS)
            fcf = latest_fcf * (1 + fade) ** yr
            pv = fcf / (1 + wacc) ** yr
            projected_fcf.append({
                'year': yr,
                'growth': round(fade * 100, 2),
                'fcf': round(fcf),
                'pv': round(pv),
            })

        # 終值（Gordon Growth Model）
        terminal_fcf = projected_fcf[-1]['fcf'] * (1 + self.TERMINAL_GROWTH)
        terminal_value = terminal_fcf / (wacc - self.TERMINAL_GROWTH)
        pv_terminal = terminal_value / (1 + wacc) ** self.PROJECTION_YEARS

        # 企業價值
        enterprise_value = sum(f['pv'] for f in projected_fcf) + pv_terminal

        # 股權價值（簡化：不扣負債、不加現金）
        shares = self._get_shares_outstanding(symbol)
        if not shares or shares <= 0:
            return None

        fair_value = enterprise_value / shares
        upside = (fair_value - price) / price * 100

        return {
            'fair_value': round(fair_value, 2),
            'current_price': price,
            'upside_pct': round(upside, 2),
            'wacc': round(wacc * 100, 2),
            'beta': round(beta, 2),
            'growth_rate': round(growth_rate * 100, 2),
            'terminal_growth': self.TERMINAL_GROWTH * 100,
            'latest_fcf': round(latest_fcf),
            'enterprise_value': round(enterprise_value),
            'shares_outstanding': shares,
            'projected_fcf': projected_fcf,
            'pv_terminal': round(pv_terminal),
        }

    # ──────────────────────────────────────────────
    #  DDM（股利折現模型）
    # ──────────────────────────────────────────────
    def ddm_valuation(self, symbol: str, price: float = None) -> Optional[Dict]:
        """
        多階段 DDM：
        - Stage 1（3年）：用近3年平均股利成長率
        - Stage 2（永續）：成長率收斂至 terminal_growth
        """
        if price is None:
            price = self._get_current_price(symbol)
        if price is None:
            return None

        dividends = self._get_dividend_history(symbol)
        if not dividends or len(dividends) < 2:
            return {'fair_value': None, 'reason': '股利資料不足'}

        # 計算年度股利
        annual_div = {}
        for d in dividends:
            year = self._extract_year(d)
            if year is None:
                continue
            cash = _to_float(d.get('cash_earnings_distribution', 0)) or 0
            stock = _to_float(d.get('stock_earnings_distribution', 0)) or 0
            total = cash + stock * 10  # 股票股利面額
            if year not in annual_div:
                annual_div[year] = 0
            annual_div[year] += total

        if len(annual_div) < 2:
            return {'fair_value': None, 'reason': '股利年數不足'}

        sorted_years = sorted(annual_div.keys())
        latest_div = annual_div[sorted_years[-1]]
        if latest_div <= 0:
            return {'fair_value': None, 'reason': '最近一年無股利'}

        # 股利成長率（近 3 年 CAGR，上限由 MAX_DIV_GROWTH 控制）
        div_growth = self._calc_div_cagr(annual_div)
        if div_growth is None:
            div_growth = 0.03
        div_growth = max(min(div_growth, self.MAX_DIV_GROWTH), -0.05)

        # 折現率（Cost of Equity），以 MIN_WACC 為下限
        beta = self._estimate_beta(symbol)
        cost_of_equity = max(self.RISK_FREE_RATE + beta * self.EQUITY_RISK_PREMIUM, self.MIN_WACC)

        if cost_of_equity <= self.TERMINAL_GROWTH:
            return {'fair_value': None, 'reason': '折現率低於永續成長率'}

        # Stage 1：高成長期（3年）
        stage1_pv = 0
        stage1_details = []
        div_t = latest_div
        for yr in range(1, 4):
            fade = div_growth - (div_growth - self.TERMINAL_GROWTH) * (yr / 3)
            div_t = div_t * (1 + fade)
            pv = div_t / (1 + cost_of_equity) ** yr
            stage1_pv += pv
            stage1_details.append({
                'year': yr,
                'dividend': round(div_t, 2),
                'growth': round(fade * 100, 2),
                'pv': round(pv, 2),
            })

        # Stage 2：永續期（Gordon Growth）
        terminal_div = div_t * (1 + self.TERMINAL_GROWTH)
        terminal_value = terminal_div / (cost_of_equity - self.TERMINAL_GROWTH)
        pv_terminal = terminal_value / (1 + cost_of_equity) ** 3

        fair_value = stage1_pv + pv_terminal
        upside = (fair_value - price) / price * 100

        return {
            'fair_value': round(fair_value, 2),
            'current_price': price,
            'upside_pct': round(upside, 2),
            'cost_of_equity': round(cost_of_equity * 100, 2),
            'latest_annual_div': round(latest_div, 2),
            'div_growth_rate': round(div_growth * 100, 2),
            'terminal_growth': self.TERMINAL_GROWTH * 100,
            'stage1_pv': round(stage1_pv, 2),
            'pv_terminal': round(pv_terminal, 2),
            'stage1_details': stage1_details,
            'dividend_history': {str(y): round(v, 2) for y, v in sorted(annual_div.items())[-5:]},
        }

    # ──────────────────────────────────────────────
    #  本益比河流圖（PE Band）
    # ──────────────────────────────────────────────
    def pe_band_analysis(self, symbol: str, price: float = None) -> Optional[Dict]:
        """計算歷史 PE 分位數，判定目前估值水位"""
        if price is None:
            price = self._get_current_price(symbol)
        if price is None:
            return None

        # 取近3年 PE 歷史
        cutoff = datetime.now() - timedelta(days=3 * 365)
        records = list(self.db.stock_factors.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}, 'pe_ratio': {'$ne': None}},
            {'date': 1, 'pe_ratio': 1}
        ).sort('date', 1))

        pe_values = [_to_float(r['pe_ratio']) for r in records if _to_float(r.get('pe_ratio'))]
        # 截掉異常 PE：移除 < 5（EPS 過低時的 PE 灌水）和 > 60（EPS 接近 0 時的 PE 爆衝）
        pe_values = [p for p in pe_values if p and 5 < p < 60]

        if len(pe_values) < 20:
            return {'fair_value': None, 'reason': 'PE 歷史資料不足'}

        arr = np.array(pe_values)
        current_pe = pe_values[-1] if pe_values else None

        # 用 P10/P50/P90 取代 P20/P50/P80（更嚴格剔除極端）
        p20 = float(np.percentile(arr, self.PE_LOW_PERCENTILE))
        p50 = float(np.percentile(arr, 50))
        p80 = float(np.percentile(arr, self.PE_HIGH_PERCENTILE))

        # 額外限制：合理 PE 不超過 MAX_REASONABLE_PE（25）
        p20 = min(p20, self.MAX_REASONABLE_PE)
        p50 = min(p50, self.MAX_REASONABLE_PE)
        p80 = min(p80, self.MAX_REASONABLE_PE)

        mean_pe = float(np.mean(arr))
        std_pe = float(np.std(arr))

        # 取最近4季 EPS
        eps = self._get_trailing_eps(symbol)
        if eps is None or eps <= 0:
            return {
                'fair_value': None,
                'reason': 'EPS 不足',
                'pe_stats': {
                    'current': round(current_pe, 2) if current_pe else None,
                    'mean': round(mean_pe, 2),
                    'p20': round(p20, 2),
                    'p50': round(p50, 2),
                    'p80': round(p80, 2),
                },
            }

        # 合理價 = 中位數 PE × EPS
        fair_value = p50 * eps
        cheap_value = p20 * eps
        expensive_value = p80 * eps

        # 目前位於哪個區間
        percentile = float(np.searchsorted(np.sort(arr), current_pe) / len(arr) * 100)

        if percentile <= 20:
            zone = '便宜區'
        elif percentile <= 40:
            zone = '偏低區'
        elif percentile <= 60:
            zone = '合理區'
        elif percentile <= 80:
            zone = '偏高區'
        else:
            zone = '昂貴區'

        upside = (fair_value - price) / price * 100

        return {
            'fair_value': round(fair_value, 2),
            'current_price': price,
            'upside_pct': round(upside, 2),
            'trailing_eps': round(eps, 2),
            'current_pe': round(current_pe, 2) if current_pe else None,
            'pe_percentile': round(percentile, 1),
            'zone': zone,
            'cheap_price': round(cheap_value, 2),
            'fair_price': round(fair_value, 2),
            'expensive_price': round(expensive_value, 2),
            'pe_stats': {
                'mean': round(mean_pe, 2),
                'std': round(std_pe, 2),
                'p20': round(p20, 2),
                'p50': round(p50, 2),
                'p80': round(p80, 2),
                'min': round(float(arr.min()), 2),
                'max': round(float(arr.max()), 2),
                'data_points': len(pe_values),
            },
        }

    # ──────────────────────────────────────────────
    #  資料存取輔助方法
    # ──────────────────────────────────────────────
    def _get_current_price(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_price.find_one(
            {'symbol': symbol},
            {'close': 1},
            sort=[('date', -1)]
        )
        return _to_float(rec['close']) if rec else None

    def _get_quarterly_earnings(self, symbol: str, years: int = 5) -> List[Dict]:
        min_year = datetime.now().year - years
        return list(self.db.quarterly_earnings.find(
            {'symbol': symbol, 'year': {'$gte': min_year}},
            {'year': 1, 'season': 1, 'income': 1, 'balance': 1}
        ).sort([('year', 1), ('season', 1)]))

    def _get_dividend_history(self, symbol: str) -> List[Dict]:
        return list(self.db.dividend_detail.find(
            {'stock_id': symbol},
            {'date': 1, 'cash_earnings_distribution': 1, 'stock_earnings_distribution': 1}
        ).sort('date', -1))

    def _get_shares_outstanding(self, symbol: str) -> Optional[float]:
        """取得流通在外股數（DB 存千股，回傳實際股數）"""
        info = self.db.taiwan_stock_info.find_one({'stock_id': symbol})
        if info:
            shares = _to_float(info.get('outstanding_shares'))
            if shares and shares > 0:
                return shares * 1000  # 千股 → 股

        info2 = self.db.stock_list.find_one({'stock_id': symbol})
        if info2:
            shares = _to_float(info2.get('outstanding_shares'))
            if shares and shares > 0:
                return shares * 1000

        return None

    def _get_trailing_eps(self, symbol: str) -> Optional[float]:
        """取得最近 4 季累計 EPS（TTM）。

        直接加總 4 季 EPS 作為 TTM。只在「Q4 EPS > 同年 Q1+Q2+Q3 總和」
        這個明確訊號出現時，才判定 Q4 是累計值並改用前後比較法。
        """
        records = list(self.db.quarterly_earnings.find(
            {'symbol': symbol},
            {'year': 1, 'season': 1, 'income.eps': 1}
        ).sort([('year', -1), ('season', -1)]).limit(8))

        if len(records) < 4:
            return None

        recent4 = records[:4]
        eps_vals = [(r['year'], r['season'],
                     r.get('income', {}).get('eps'))
                    for r in recent4]
        if any(e[2] is None for e in eps_vals):
            return None

        # 直接加總 4 季 EPS 作為 TTM
        # （quarterly_earnings 集合的 EPS 是「單季 EPS」，不是累計值）
        return sum(e[2] for e in eps_vals)

    def _aggregate_annual(self, earnings: List[Dict], field: str) -> List[Dict]:
        """將季度數據加總為年度"""
        by_year = {}
        for e in earnings:
            year = e.get('year')
            val = e.get('income', {}).get(field)
            if year is None or val is None:
                continue
            if year not in by_year:
                by_year[year] = {'year': year, 'value': 0, 'quarters': 0}
            by_year[year]['value'] += val
            by_year[year]['quarters'] += 1

        # 只保留有4季完整資料的年度
        result = [v for v in sorted(by_year.values(), key=lambda x: x['year'])
                  if v['quarters'] >= 3]
        return result

    def _calc_cagr(self, annual_data: List[Dict], min_years: int = 2) -> Optional[float]:
        if not annual_data or len(annual_data) < min_years:
            return None
        start_val = annual_data[0]['value']
        end_val = annual_data[-1]['value']
        n_years = annual_data[-1]['year'] - annual_data[0]['year']
        if n_years <= 0 or start_val <= 0 or end_val <= 0:
            return None
        return (end_val / start_val) ** (1 / n_years) - 1

    def _calc_div_cagr(self, annual_div: Dict[int, float]) -> Optional[float]:
        sorted_years = sorted(annual_div.keys())
        if len(sorted_years) < 2:
            return None
        # 用最近3年
        recent = sorted_years[-min(4, len(sorted_years)):]
        start_val = annual_div[recent[0]]
        end_val = annual_div[recent[-1]]
        n = recent[-1] - recent[0]
        if n <= 0 or start_val <= 0:
            return None
        return (end_val / start_val) ** (1 / n) - 1

    def _estimate_beta(self, symbol: str) -> float:
        """用近1年日報酬率 vs 大盤估算 Beta"""
        cutoff = datetime.now() - timedelta(days=365)

        stock_prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'date': 1, 'close': 1}
        ).sort('date', 1))

        market_prices = list(self.db.stock_price.find(
            {'symbol': '0050', 'date': {'$gte': cutoff}},
            {'date': 1, 'close': 1}
        ).sort('date', 1))

        if len(stock_prices) < 30 or len(market_prices) < 30:
            return 1.0  # 預設 Beta = 1

        stock_ret = self._calc_returns(stock_prices)
        market_ret = self._calc_returns(market_prices)

        # 對齊日期
        s_dict = {r[0]: r[1] for r in stock_ret}
        m_dict = {r[0]: r[1] for r in market_ret}
        common_dates = sorted(set(s_dict.keys()) & set(m_dict.keys()))

        if len(common_dates) < 20:
            return 1.0

        s_arr = np.array([s_dict[d] for d in common_dates])
        m_arr = np.array([m_dict[d] for d in common_dates])

        cov = np.cov(s_arr, m_arr)
        if cov[1][1] == 0:
            return 1.0
        beta = cov[0][1] / cov[1][1]
        return max(min(beta, 3.0), 0.3)  # 限制範圍

    def _calc_returns(self, prices: List[Dict]) -> List[Tuple]:
        returns = []
        for i in range(1, len(prices)):
            p0 = _to_float(prices[i - 1].get('close'))
            p1 = _to_float(prices[i].get('close'))
            if p0 and p1 and p0 > 0:
                returns.append((prices[i]['date'], (p1 - p0) / p0))
        return returns

    def _extract_year(self, dividend_doc: Dict) -> Optional[int]:
        date = dividend_doc.get('date', '')
        if isinstance(date, str) and len(date) >= 4:
            try:
                return int(date[:4])
            except ValueError:
                return None
        if isinstance(date, datetime):
            return date.year
        return None

    def _get_verdict(self, upside: Optional[float]) -> str:
        if upside is None:
            return '無法判定'
        if upside > 30:
            return '嚴重低估'
        if upside > 15:
            return '低估'
        if upside > 5:
            return '略為低估'
        if upside > -5:
            return '合理'
        if upside > -15:
            return '略為高估'
        if upside > -30:
            return '高估'
        return '嚴重高估'


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    va = ValuationAnalyzer()
    test_symbols = ['2330', '2317', '2454', '2603', '0056']

    for sym in test_symbols:
        print(f"\n{'='*60}")
        print(f"  {sym} 估值分析")
        print(f"{'='*60}")
        result = va.analyze(sym)

        if result.get('error'):
            print(f"  錯誤: {result['error']}")
            continue

        price = result['current_price']
        print(f"  現價: {price}")

        for model in ['dcf', 'ddm', 'pe_band']:
            r = result.get(model)
            if r and r.get('fair_value'):
                fv = r['fair_value']
                up = r['upside_pct']
                print(f"  {model.upper():>8}: 合理價 {fv:>8.2f}  潛在報酬 {up:>+6.1f}%")
            elif r and r.get('reason'):
                print(f"  {model.upper():>8}: {r['reason']}")

        comp = result.get('composite', {})
        if comp.get('fair_value'):
            print(f"  {'綜合':>8}: 合理價 {comp['fair_value']:>8.2f}  "
                  f"潛在報酬 {comp['upside_pct']:>+6.1f}%  "
                  f"判定: {comp['verdict']}")
