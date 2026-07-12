#!/usr/bin/env python3
"""
綜合選股評分模組
===============
整合估值、風險、同業排名、情緒、技術面，產出「綜合選股評分」排行榜。

Usage:
    from src.analysis.stock_ranker import StockRanker
    sr = StockRanker()
    top20 = sr.rank(limit=20)
    detail = sr.score_stock('2330')
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
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


class StockRanker:
    """綜合選股評分器"""

    # 評分權重
    WEIGHTS = {
        'value': 0.25,       # 估值（PE/PB/殖利率）
        'quality': 0.20,     # 品質（ROE/營業利益率）
        'momentum': 0.15,    # 動能（RSI/月報酬）
        'safety': 0.15,      # 安全性（波動度/最大回撤）
        'institutional': 0.15,  # 籌碼（外資/投信）
        'growth': 0.10,      # 成長（營收 YoY）
    }

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._health_cache: Dict[str, Dict] = {}

    def _get_health(self, symbol: str) -> Optional[Dict]:
        """惰性快取財報分析結果，避免對同一股呼叫多次。"""
        if symbol not in self._health_cache:
            from .financial_health import FinancialHealthAnalyzer
            if not hasattr(self, '_fh'):
                self._fh = FinancialHealthAnalyzer()
            r = self._fh.analyze_stock(symbol)
            self._health_cache[symbol] = r if 'error' not in r else None
        return self._health_cache[symbol]

    def rank(self, limit: int = 30, exclude_etf: bool = True,
             min_pe: float = 0, max_pe: float = 100,
             financial_check: bool = True) -> List[Dict]:
        """全市場綜合排名

        financial_check=True 會剔除 TTM 虧損 / 高負債 / 淨利率為負的地雷股。
        """
        candidates = self._load_candidates(exclude_etf)
        logger.info(f'候選股票: {len(candidates)} 支')

        if not candidates:
            return []

        # 計算各維度百分位
        scored = []
        for sym, data in candidates.items():
            score = self._score_stock_data(sym, data, candidates)
            if score is not None:
                pe = _to_float(data.get('pe_ratio'))
                if pe and (pe < min_pe or pe > max_pe):
                    continue
                scored.append(score)

        scored.sort(key=lambda x: x['total_score'], reverse=True)
        logger.info(f'有效評分: {len(scored)} 支')

        # 財報健康篩檢（剔除地雷股）
        if financial_check:
            from .financial_filter import FinancialFilter
            ff = FinancialFilter()
            # 先只檢查前 limit*3 支，避免全市場跑太久
            pre_filter = scored[:limit * 3]
            healthy = []
            filtered_out = []
            for s in pre_filter:
                if ff.is_healthy(s['symbol']):
                    healthy.append(s)
                else:
                    filtered_out.append(s['symbol'])
            logger.info(f'財報篩檢後: {len(healthy)} 支（剔除 {len(filtered_out)} 支地雷股）')
            scored = healthy

        # 加排名
        for i, s in enumerate(scored):
            s['rank'] = i + 1

        return scored[:limit]

    def score_stock(self, symbol: str) -> Optional[Dict]:
        """單股詳細評分"""
        candidates = self._load_candidates(exclude_etf=False)
        data = candidates.get(symbol)
        if not data:
            return {'symbol': symbol, 'error': '無因子資料'}

        return self._score_stock_data(symbol, data, candidates)

    def _score_stock_data(self, symbol: str, data: Dict,
                          all_data: Dict) -> Optional[Dict]:
        """計算單股綜合評分"""
        scores = {}

        # 1. 估值分數（PE 低好、PB 低好、殖利率高好）
        pe = _to_float(data.get('pe_ratio'))
        pb = _to_float(data.get('pb_ratio'))
        dy = _to_float(data.get('dividend_yield'))

        val_scores = []
        if pe and 0 < pe < 200:
            val_scores.append(self._percentile_rank_lower(pe, all_data, 'pe_ratio'))
        if pb and 0 < pb < 50:
            val_scores.append(self._percentile_rank_lower(pb, all_data, 'pb_ratio'))
        if dy is not None and dy >= 0:
            val_scores.append(self._percentile_rank_higher(dy, all_data, 'dividend_yield'))

        scores['value'] = np.mean(val_scores) if val_scores else 50

        # 2. 品質分數（優先用 FinancialHealthAnalyzer 的獲利 + 品質綜合分；失敗則退回 ROE + 營益率）
        qual_scores = []
        health = self._get_health(symbol)
        if health:
            # 新邏輯：獲利 50% + 品質 30% + 安全 20%
            hs = health['scores']
            qual_scores.append(
                hs['profitability'] * 0.5 + hs['quality'] * 0.3 + hs['safety'] * 0.2
            )
        else:
            roe = _to_float(data.get('roe'))
            om = _to_float(data.get('operating_margin'))
            if roe is not None:
                qual_scores.append(self._percentile_rank_higher(roe, all_data, 'roe'))
            if om is not None:
                qual_scores.append(self._percentile_rank_higher(om, all_data, 'operating_margin'))

        scores['quality'] = np.mean(qual_scores) if qual_scores else 50

        # 3. 動能分數（RSI 30-70 中性，月報酬高好）
        rsi = _to_float(data.get('rsi_14'))
        ret = _to_float(data.get('return_1m'))

        mom_scores = []
        if rsi is not None:
            # RSI 50 附近最好，過高過低扣分
            rsi_score = max(0, 100 - abs(rsi - 50) * 2)
            mom_scores.append(rsi_score)
        if ret is not None:
            mom_scores.append(self._percentile_rank_higher(ret, all_data, 'return_1m'))

        scores['momentum'] = np.mean(mom_scores) if mom_scores else 50

        # 4. 安全性（波動度低好）
        vol = _to_float(data.get('volatility_30d'))
        if vol is not None and vol > 0:
            scores['safety'] = self._percentile_rank_lower(vol, all_data, 'volatility_30d')
        else:
            scores['safety'] = 50

        # 5. 籌碼（外資買超好）
        inst = self._get_institutional_score(symbol)
        scores['institutional'] = inst if inst is not None else 50

        # 6. 成長（營收 YoY 高好）
        growth = self._get_revenue_growth(symbol)
        scores['growth'] = min(max(growth + 50, 0), 100) if growth is not None else 50

        # 加權總分
        total = sum(scores[k] * self.WEIGHTS[k] for k in self.WEIGHTS)

        # 取名稱和股價
        name = self._get_stock_name(symbol)
        price = self._get_latest_price(symbol)

        return {
            'symbol': symbol,
            'name': name,
            'price': price,
            'total_score': round(total, 1),
            'grade': self._score_to_grade(total),
            'scores': {k: round(v, 1) for k, v in scores.items()},
            'metrics': {
                'pe_ratio': round(pe, 2) if pe else None,
                'pb_ratio': round(pb, 2) if pb else None,
                'dividend_yield': round(dy, 2) if dy else None,
                'roe': (round(health['dupont']['roe_pct'], 2)
                        if health and health.get('dupont', {}).get('roe_pct') is not None
                        else None),
                'rsi_14': round(rsi, 1) if rsi else None,
                'return_1m': round(ret, 2) if ret else None,
            },
        }

    # ──────────────────────────────────────────────
    #  資料載入
    # ──────────────────────────────────────────────
    def _load_candidates(self, exclude_etf: bool = True) -> Dict[str, Dict]:
        """載入全市場最新因子。
        注意：stock_factors 為多來源（TWSE 寫 pe/pb/殖利率；factor_calc 寫 roe/rsi 等，
        且最新一筆常是 factor_calc 無 pe）。故用『近30天取每欄首個非null』而非 naive $first，
        否則最新筆無 pe → 候選全被剔除（與 senvision scanner.load_fundamentals_cache 同模式）。"""
        FIELDS = ['pe_ratio', 'pb_ratio', 'dividend_yield', 'roe',
                  'operating_margin', 'rsi_14', 'return_1m', 'volatility_30d']
        cutoff = datetime.now() - timedelta(days=30)
        pipeline = [
            {'$match': {'date': {'$gte': cutoff}}},
            {'$sort': {'date': -1}},
            {'$group': {
                '_id': '$symbol',
                **{f'{f}_arr': {'$push': f'${f}'} for f in FIELDS},
                'date': {'$first': '$date'},
            }},
            {'$project': {
                'date': 1,
                **{f: {'$first': {'$filter': {
                    'input': f'${f}_arr', 'cond': {'$ne': ['$$this', None]},
                }}} for f in FIELDS},
            }},
        ]

        results = {}
        for doc in self.db.stock_factors.aggregate(pipeline, allowDiskUse=True):
            sym = doc['_id']
            if exclude_etf and (sym.startswith('00') or not sym.isdigit()):
                continue
            if len(sym) != 4:
                continue
            # 至少要有 PE 或殖利率
            if _to_float(doc.get('pe_ratio')) is None and _to_float(doc.get('dividend_yield')) is None:
                continue
            results[sym] = doc

        return results

    def _percentile_rank_higher(self, value: float, all_data: Dict,
                                field: str) -> float:
        """百分位排名（值越高越好）"""
        all_vals = [_to_float(d.get(field)) for d in all_data.values()]
        all_vals = [v for v in all_vals if v is not None]
        if not all_vals:
            return 50
        arr = np.array(all_vals)
        return float(np.searchsorted(np.sort(arr), value) / len(arr) * 100)

    def _percentile_rank_lower(self, value: float, all_data: Dict,
                               field: str) -> float:
        """百分位排名（值越低越好）"""
        return 100 - self._percentile_rank_higher(value, all_data, field)

    def _get_institutional_score(self, symbol: str) -> Optional[float]:
        """近 5 日法人買賣超評分"""
        cutoff = datetime.now() - timedelta(days=10)
        flows = list(self.db.institutional_flow.find(
            {'stock_id': symbol, 'date': {'$gte': cutoff}},
            {'foreign_net': 1, 'trust_net': 1}
        ).sort('date', -1).limit(5))

        if not flows:
            return None

        foreign = sum(_to_float(f.get('foreign_net', 0)) or 0 for f in flows)
        trust = sum(_to_float(f.get('trust_net', 0)) or 0 for f in flows)

        # 正規化到 0-100
        if foreign > 0 and trust > 0:
            return 80
        elif foreign > 0 or trust > 0:
            return 65
        elif foreign < 0 and trust < 0:
            return 20
        elif foreign < 0 or trust < 0:
            return 35
        return 50

    def _get_revenue_growth(self, symbol: str) -> Optional[float]:
        """最新月營收 YoY"""
        rec = self.db.monthly_revenue.find_one(
            {'symbol': symbol, 'yoy_growth': {'$exists': True}},
            {'yoy_growth': 1},
            sort=[('year_month', -1)]
        )
        if rec:
            v = _to_float(rec.get('yoy_growth'))
            # 截斷極端基期效應(如建案完工認列致 +87447%；官方數值正確但會汙染排名)：>500% 視為 500
            return min(v, 500.0) if v is not None else None
        return None

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_price.find_one(
            {'symbol': symbol}, {'close': 1}, sort=[('date', -1)])
        return _to_float(rec['close']) if rec else None

    def _get_stock_name(self, symbol: str) -> str:
        for col in ['taiwan_stock_info', 'stock_list']:
            try:
                rec = self.db[col].find_one({'stock_id': symbol}, {'stock_name': 1, 'name': 1})
                if rec:
                    return rec.get('stock_name', rec.get('name', ''))
            except Exception:
                pass
        rec = self.db.stock_price.find_one({'symbol': symbol}, {'name': 1})
        return rec.get('name', '') if rec else ''

    def _score_to_grade(self, score: float) -> str:
        if score >= 75:
            return 'A（強力推薦）'
        elif score >= 65:
            return 'B+（值得關注）'
        elif score >= 55:
            return 'B（中性偏多）'
        elif score >= 45:
            return 'C（中性）'
        else:
            return 'D（暫不建議）'


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    sr = StockRanker()

    print(f"\n{'='*75}")
    print("  綜合選股評分排行榜 Top 20")
    print(f"{'='*75}")

    top = sr.rank(limit=20)

    print(f"\n  {'名次':>3} {'代號':<6} {'名稱':<8} {'股價':>7} {'總分':>5} "
          f"{'估值':>4} {'品質':>4} {'動能':>4} {'安全':>4} {'籌碼':>4} {'成長':>4}  等級")
    print(f"  {'-'*72}")

    for s in top:
        sc = s['scores']
        print(f"  {s['rank']:>3} {s['symbol']:<6} {s['name']:<8} "
              f"{s['price'] or 0:>7.1f} {s['total_score']:>5.1f} "
              f"{sc['value']:>4.0f} {sc['quality']:>4.0f} "
              f"{sc['momentum']:>4.0f} {sc['safety']:>4.0f} "
              f"{sc['institutional']:>4.0f} {sc['growth']:>4.0f}  "
              f"{s['grade']}")
