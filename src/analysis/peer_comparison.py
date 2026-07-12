#!/usr/bin/env python3
"""
同業比較分析模組
===============
依產業分群，提供個股在同業中的相對估值排名與優劣勢分析。

Usage:
    from src.analysis.peer_comparison import PeerComparison
    pc = PeerComparison()
    result = pc.analyze('2330')
    ranking = pc.industry_ranking('半導體業')
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


class PeerComparison:
    """同業比較分析器"""

    # 比較指標
    METRICS = [
        ('pe_ratio', 'PE', 'lower_better'),
        ('pb_ratio', 'PB', 'lower_better'),
        ('dividend_yield', '殖利率', 'higher_better'),
        ('roe', 'ROE', 'higher_better'),
        ('operating_margin', '營業利益率', 'higher_better'),
        ('rsi_14', 'RSI', 'neutral'),
        ('return_1m', '月報酬', 'higher_better'),
    ]

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._industry_cache = {}

    # ──────────────────────────────────────────────
    #  個股同業比較
    # ──────────────────────────────────────────────
    def analyze(self, symbol: str) -> Dict:
        """個股 vs 同業比較分析"""
        industry = self._get_industry(symbol)
        if not industry:
            return {'symbol': symbol, 'error': '無法取得產業分類'}

        # 取同業所有股票的最新因子
        peers = self._get_industry_peers(industry)
        if len(peers) < 3:
            return {'symbol': symbol, 'error': f'{industry} 同業數量不足 ({len(peers)} 支)'}

        # 找目標股票
        target = None
        for p in peers:
            if p['symbol'] == symbol:
                target = p
                break

        if target is None:
            return {'symbol': symbol, 'error': '目標股票無因子資料'}

        # 計算各指標排名與百分位
        comparisons = []
        total_score = 0
        max_score = 0

        for field, label, direction in self.METRICS:
            values = [(_to_float(p.get(field)),  p['symbol']) for p in peers]
            values = [(v, s) for v, s in values if v is not None and not np.isnan(v)]

            target_val = _to_float(target.get(field))
            if target_val is None or len(values) < 3:
                comparisons.append({
                    'metric': label, 'field': field,
                    'value': None, 'rank': None, 'percentile': None, 'grade': 'N/A',
                })
                continue

            # 排序
            if direction == 'lower_better':
                sorted_vals = sorted(values, key=lambda x: x[0])
            else:
                sorted_vals = sorted(values, key=lambda x: -x[0])

            rank = next((i + 1 for i, (v, s) in enumerate(sorted_vals) if s == symbol), None)
            percentile = (1 - (rank - 1) / len(sorted_vals)) * 100 if rank else 0

            all_vals = [v for v, _ in values]
            median = float(np.median(all_vals))
            mean = float(np.mean(all_vals))

            # 評分 (百分位 → 分數)
            if direction != 'neutral':
                grade, score = self._percentile_to_grade(percentile)
                total_score += score
                max_score += 5
            else:
                grade = '中性'
                score = 0

            comparisons.append({
                'metric': label,
                'field': field,
                'value': round(target_val, 2),
                'rank': rank,
                'total_peers': len(sorted_vals),
                'percentile': round(percentile, 1),
                'industry_median': round(median, 2),
                'industry_mean': round(mean, 2),
                'grade': grade,
                'direction': direction,
            })

        # 綜合評分
        composite_score = total_score / max_score * 100 if max_score > 0 else 0
        composite_grade = self._score_to_grade(composite_score)

        # 找出優勢與劣勢
        strengths = [c for c in comparisons if c.get('percentile') and c['percentile'] >= 70 and c['grade'] != 'N/A']
        weaknesses = [c for c in comparisons if c.get('percentile') and c['percentile'] <= 30 and c['grade'] != 'N/A']

        # Top 5 同業
        top5 = self._get_top_peers(peers, 5)

        return {
            'symbol': symbol,
            'name': self._get_stock_name(symbol),
            'industry': industry,
            'peer_count': len(peers),
            'comparisons': comparisons,
            'composite': {
                'score': round(composite_score, 1),
                'grade': composite_grade,
            },
            'strengths': [{'metric': s['metric'], 'value': s['value'],
                           'rank': f"{s['rank']}/{s['total_peers']}"}
                          for s in strengths],
            'weaknesses': [{'metric': w['metric'], 'value': w['value'],
                            'rank': f"{w['rank']}/{w['total_peers']}"}
                           for w in weaknesses],
            'top5_peers': top5,
        }

    # ──────────────────────────────────────────────
    #  產業排名
    # ──────────────────────────────────────────────
    def industry_ranking(self, industry: str, sort_by: str = 'composite',
                         limit: int = 20) -> Dict:
        """產業內綜合排名"""
        peers = self._get_industry_peers(industry)
        if len(peers) < 3:
            return {'error': f'{industry} 同業數量不足'}

        # 計算每支股票的綜合分數
        scored = []
        for peer in peers:
            score = self._calc_composite_score(peer, peers)
            if score is not None:
                price = self._get_latest_price(peer['symbol'])
                scored.append({
                    'symbol': peer['symbol'],
                    'name': self._get_stock_name(peer['symbol']),
                    'price': price,
                    'score': round(score, 1),
                    'pe_ratio': round(_to_float(peer.get('pe_ratio')) or 0, 2),
                    'pb_ratio': round(_to_float(peer.get('pb_ratio')) or 0, 2),
                    'dividend_yield': round(_to_float(peer.get('dividend_yield')) or 0, 2),
                    'roe': round(_to_float(peer.get('roe')) or 0, 2),
                    'operating_margin': round(_to_float(peer.get('operating_margin')) or 0, 2),
                })

        scored.sort(key=lambda x: x['score'], reverse=True)

        # 產業統計
        pe_vals = [_to_float(p.get('pe_ratio')) for p in peers if _to_float(p.get('pe_ratio'))]
        pb_vals = [_to_float(p.get('pb_ratio')) for p in peers if _to_float(p.get('pb_ratio'))]
        dy_vals = [_to_float(p.get('dividend_yield')) for p in peers if _to_float(p.get('dividend_yield'))]
        roe_vals = [_to_float(p.get('roe')) for p in peers if _to_float(p.get('roe'))]

        return {
            'industry': industry,
            'total_stocks': len(peers),
            'ranked_stocks': len(scored),
            'ranking': scored[:limit],
            'industry_stats': {
                'pe_median': round(float(np.median(pe_vals)), 2) if pe_vals else None,
                'pb_median': round(float(np.median(pb_vals)), 2) if pb_vals else None,
                'dividend_yield_median': round(float(np.median(dy_vals)), 2) if dy_vals else None,
                'roe_median': round(float(np.median(roe_vals)), 2) if roe_vals else None,
            },
        }

    # ──────────────────────────────────────────────
    #  產業列表
    # ──────────────────────────────────────────────
    def list_industries(self) -> List[Dict]:
        """列出所有產業及股票數"""
        industries = self.db.monthly_revenue.distinct('industry')
        result = []
        for ind in sorted(industries):
            if not ind:
                continue
            symbols = self.db.monthly_revenue.distinct('symbol', {'industry': ind})
            result.append({'industry': ind, 'count': len(symbols)})
        return result

    # ──────────────────────────────────────────────
    #  輔助方法
    # ──────────────────────────────────────────────
    def _get_industry(self, symbol: str) -> Optional[str]:
        if symbol in self._industry_cache:
            return self._industry_cache[symbol]

        # 從 monthly_revenue（最準確的產業分類）
        rec = self.db.monthly_revenue.find_one({'symbol': symbol}, {'industry': 1})
        if rec and rec.get('industry'):
            self._industry_cache[symbol] = rec['industry']
            return rec['industry']

        # 從 taiwan_stock_info
        info = self.db.taiwan_stock_info.find_one({'stock_id': symbol}, {'industry_category': 1})
        if info and info.get('industry_category'):
            self._industry_cache[symbol] = info['industry_category']
            return info['industry_category']

        return None

    def _get_industry_peers(self, industry: str) -> List[Dict]:
        """取得同業所有股票的最新因子"""
        # 取產業內所有股票
        symbols = self.db.monthly_revenue.distinct('symbol', {'industry': industry})

        if not symbols:
            return []

        # 批量查詢最新因子。stock_factors 多來源(最新筆常無 pe) → 用『近30天每欄首個非null』，
        # 否則 PE/PB 等同業排名全 null（與 stock_ranker/scanner 同模式）。
        from datetime import datetime, timedelta
        _F = ['pe_ratio', 'pb_ratio', 'dividend_yield', 'roe',
              'operating_margin', 'rsi_14', 'return_1m']
        _cut = datetime.now() - timedelta(days=30)
        pipeline = [
            {'$match': {'symbol': {'$in': symbols}, 'date': {'$gte': _cut}}},
            {'$sort': {'date': -1}},
            {'$group': {'_id': '$symbol',
                        **{f'{f}_arr': {'$push': f'${f}'} for f in _F},
                        'date': {'$first': '$date'}}},
            {'$project': {'date': 1,
                          **{f: {'$first': {'$filter': {
                              'input': f'${f}_arr', 'cond': {'$ne': ['$$this', None]}}}} for f in _F}}},
        ]

        results = list(self.db.stock_factors.aggregate(pipeline))

        peers = []
        for r in results:
            r['symbol'] = r.pop('_id')
            # 過濾沒有任何有效數據的
            has_data = any(_to_float(r.get(f)) is not None for f, _, _ in self.METRICS)
            if has_data:
                peers.append(r)

        return peers

    def _calc_composite_score(self, stock: Dict, peers: List[Dict]) -> Optional[float]:
        """計算單股綜合分數"""
        total = 0
        count = 0

        for field, _, direction in self.METRICS:
            if direction == 'neutral':
                continue
            val = _to_float(stock.get(field))
            if val is None:
                continue

            all_vals = [_to_float(p.get(field)) for p in peers]
            all_vals = [v for v in all_vals if v is not None and not np.isnan(v)]
            if len(all_vals) < 3:
                continue

            if direction == 'lower_better':
                sorted_vals = sorted(all_vals)
            else:
                sorted_vals = sorted(all_vals, reverse=True)

            rank = sorted_vals.index(val) + 1 if val in sorted_vals else len(sorted_vals)
            percentile = (1 - (rank - 1) / len(sorted_vals)) * 100

            total += percentile
            count += 1

        return total / count if count > 0 else None

    def _get_top_peers(self, peers: List[Dict], n: int) -> List[Dict]:
        """取得前 N 名同業"""
        scored = []
        for p in peers:
            score = self._calc_composite_score(p, peers)
            if score is not None:
                scored.append({
                    'symbol': p['symbol'],
                    'name': self._get_stock_name(p['symbol']),
                    'score': round(score, 1),
                })
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:n]

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_price.find_one(
            {'symbol': symbol}, {'close': 1}, sort=[('date', -1)]
        )
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

    def _percentile_to_grade(self, percentile: float):
        if percentile >= 80:
            return 'A', 5
        elif percentile >= 60:
            return 'B+', 4
        elif percentile >= 40:
            return 'B', 3
        elif percentile >= 20:
            return 'C', 2
        else:
            return 'D', 1

    def _score_to_grade(self, score: float) -> str:
        if score >= 80:
            return 'A（同業領先）'
        elif score >= 65:
            return 'B+（優於平均）'
        elif score >= 50:
            return 'B（接近平均）'
        elif score >= 35:
            return 'C（低於平均）'
        else:
            return 'D（同業落後）'


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    pc = PeerComparison()

    # 個股分析
    for sym in ['2330', '2317', '2603']:
        print(f"\n{'='*60}")
        r = pc.analyze(sym)
        if r.get('error'):
            print(f"  {sym}: {r['error']}")
            continue

        print(f"  {sym} {r['name']} — {r['industry']} ({r['peer_count']} 支)")
        print(f"  綜合: {r['composite']['score']:.1f} 分 {r['composite']['grade']}")

        print(f"\n  {'指標':<10} {'數值':>8} {'排名':>10} {'百分位':>6} {'評等':>4}")
        print(f"  {'-'*44}")
        for c in r['comparisons']:
            if c.get('rank'):
                print(f"  {c['metric']:<10} {c['value']:>8.2f} "
                      f"{c['rank']:>3}/{c['total_peers']:<4} "
                      f"{c['percentile']:>5.1f}% {c['grade']:>4}")

        if r['strengths']:
            print(f"\n  ✅ 優勢: {', '.join(f'{s['metric']}({s['rank']})' for s in r['strengths'])}")
        if r['weaknesses']:
            print(f"  ⚠️ 劣勢: {', '.join(f'{w['metric']}({w['rank']})' for w in r['weaknesses'])}")

        if r.get('top5_peers'):
            print(f"\n  同業 Top 5:")
            for i, p in enumerate(r['top5_peers'], 1):
                marker = ' ←' if p['symbol'] == sym else ''
                print(f"    {i}. {p['symbol']} {p['name']} ({p['score']:.1f}分){marker}")

    # 產業排名
    print(f"\n{'='*60}")
    print("  半導體業排名 Top 10")
    ranking = pc.industry_ranking('半導體業', limit=10)
    if not ranking.get('error'):
        stats = ranking['industry_stats']
        print(f"  產業中位數: PE={stats['pe_median']}  PB={stats['pb_median']}  "
              f"殖利率={stats['dividend_yield_median']}%  ROE={stats['roe_median']}%")
        print(f"\n  {'名次':>4} {'代號':<6} {'名稱':<8} {'分數':>5} {'PE':>6} {'殖利率':>6} {'ROE':>6}")
        for i, s in enumerate(ranking['ranking'], 1):
            print(f"  {i:>4} {s['symbol']:<6} {s['name']:<8} "
                  f"{s['score']:>5.1f} {s['pe_ratio']:>6.1f} "
                  f"{s['dividend_yield']:>5.1f}% {s['roe']:>5.1f}%")
