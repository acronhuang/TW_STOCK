#!/usr/bin/env python3
"""
總經數據整合模組
===============
台灣利率、匯率、CPI、M1B/M2、景氣燈號等總經指標。
資料來源：央行 API、主計處、FinMind。

Usage:
    from src.analysis.macro_indicators import MacroAnalyzer
    ma = MacroAnalyzer()
    overview = ma.overview()          # 總經儀表板
    signal = ma.market_signal()       # 大盤方向判斷
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import requests
import numpy as np
from pymongo import MongoClient

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'
# 央行公開資料 API（無需 token）
CBC_API = 'https://www.cbc.gov.tw/public/data/OpenData'


class MacroAnalyzer:
    """總經指標分析器"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.finmind_token = os.getenv('FINMIND_API_TOKEN', '')
        self._ensure_collection()

    def _ensure_collection(self):
        if 'macro_indicators' not in self.db.list_collection_names():
            self.db.create_collection('macro_indicators')
            self.db.macro_indicators.create_index([('indicator', 1), ('date', -1)])

    # ──────────────────────────────────────────────
    #  總經儀表板
    # ──────────────────────────────────────────────
    def overview(self) -> Dict:
        """總經數據總覽"""
        interest_rate = self._get_interest_rate()
        exchange_rate = self._get_exchange_rate()
        cpi = self._get_cpi()
        money_supply = self._get_money_supply()
        leading = self._get_leading_indicator()
        taiex = self._get_taiex_summary()

        return {
            'interest_rate': interest_rate,
            'exchange_rate': exchange_rate,
            'cpi': cpi,
            'money_supply': money_supply,
            'leading_indicator': leading,
            'taiex': taiex,
            'updated_at': datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────
    #  大盤方向判斷
    # ──────────────────────────────────────────────
    def market_signal(self) -> Dict:
        """綜合總經指標判斷大盤方向"""
        signals = []

        # 1. 貨幣供給（M1B > M2 = 資金行情）
        ms = self._get_money_supply()
        if ms and ms.get('m1b_yoy') is not None and ms.get('m2_yoy') is not None:
            m1b_m2 = ms['m1b_yoy'] - ms['m2_yoy']
            if m1b_m2 > 0:
                signals.append(('貨幣黃金交叉', 'bullish', f'M1B({ms["m1b_yoy"]:.1f}%) > M2({ms["m2_yoy"]:.1f}%)'))
            else:
                signals.append(('貨幣死亡交叉', 'bearish', f'M1B({ms["m1b_yoy"]:.1f}%) < M2({ms["m2_yoy"]:.1f}%)'))

        # 2. 利率（低利率 = 有利股市）
        ir = self._get_interest_rate()
        if ir and ir.get('discount_rate') is not None:
            rate = ir['discount_rate']
            if rate < 2.0:
                signals.append(('低利率環境', 'bullish', f'重貼現率 {rate:.3f}%'))
            elif rate > 3.0:
                signals.append(('高利率環境', 'bearish', f'重貼現率 {rate:.3f}%'))
            else:
                signals.append(('利率中性', 'neutral', f'重貼現率 {rate:.3f}%'))

        # 3. CPI（通膨 > 3% = 緊縮壓力）
        cpi = self._get_cpi()
        if cpi and cpi.get('yoy') is not None:
            if cpi['yoy'] > 3:
                signals.append(('通膨偏高', 'bearish', f'CPI YoY {cpi["yoy"]:.2f}%'))
            elif cpi['yoy'] < 1:
                signals.append(('通縮風險', 'bearish', f'CPI YoY {cpi["yoy"]:.2f}%'))
            else:
                signals.append(('通膨溫和', 'bullish', f'CPI YoY {cpi["yoy"]:.2f}%'))

        # 4. 匯率（台幣升值 = 外資流入）
        fx = self._get_exchange_rate()
        if fx and fx.get('usd_twd') is not None and fx.get('change_1m') is not None:
            if fx['change_1m'] < -0.5:
                signals.append(('台幣升值', 'bullish', f'USD/TWD {fx["usd_twd"]:.2f} (月變 {fx["change_1m"]:+.2f})'))
            elif fx['change_1m'] > 0.5:
                signals.append(('台幣貶值', 'bearish', f'USD/TWD {fx["usd_twd"]:.2f} (月變 {fx["change_1m"]:+.2f})'))

        # 5. 外資動向
        taiex = self._get_taiex_summary()
        if taiex and taiex.get('foreign_net_5d') is not None:
            fn = taiex['foreign_net_5d']
            if fn > 0:
                signals.append(('外資近5日買超', 'bullish', f'{fn/1e8:.1f}億'))
            else:
                signals.append(('外資近5日賣超', 'bearish', f'{fn/1e8:.1f}億'))

        # 綜合評分
        bullish = sum(1 for _, s, _ in signals if s == 'bullish')
        bearish = sum(1 for _, s, _ in signals if s == 'bearish')
        total = len(signals)

        if total == 0:
            score = 0
        else:
            score = (bullish - bearish) / total * 100

        if score > 30:
            verdict = '偏多（總經環境有利）'
        elif score > 0:
            verdict = '中性偏多'
        elif score > -30:
            verdict = '中性偏空'
        else:
            verdict = '偏空（總經環境不利）'

        return {
            'score': round(score, 1),
            'verdict': verdict,
            'bullish_count': bullish,
            'bearish_count': bearish,
            'signals': [{'name': n, 'direction': d, 'detail': det}
                        for n, d, det in signals],
        }

    # ──────────────────────────────────────────────
    #  各項指標取得
    # ──────────────────────────────────────────────
    def _get_interest_rate(self) -> Optional[Dict]:
        """台灣央行利率"""
        # 先查本地
        local = self.db.macro_indicators.find_one(
            {'indicator': 'interest_rate'},
            sort=[('date', -1)]
        )
        if local and self._is_fresh(local, days=30):
            return local.get('data')

        # FinMind
        data = self._finmind_fetch('TaiwanInterestRate', days=90)
        if data:
            latest = data[-1]
            result = {
                'date': latest.get('date', ''),
                'discount_rate': latest.get('discount_rate', latest.get('rate')),
            }
            self._save_indicator('interest_rate', result)
            return result

        return local.get('data') if local else None

    def _get_exchange_rate(self) -> Optional[Dict]:
        """美元/台幣匯率"""
        local = self.db.macro_indicators.find_one(
            {'indicator': 'exchange_rate'},
            sort=[('date', -1)]
        )
        if local and self._is_fresh(local, days=7):
            return local.get('data')

        data = self._finmind_fetch('TaiwanExchangeRate', days=60)
        if data:
            usd = [d for d in data if d.get('currency', '') in ('USD', 'USD/NTD', '美元')]
            if usd:
                latest = usd[-1]
                rate = latest.get('spot_buy', latest.get('cash_buy', latest.get('rate', 0)))

                # 計算月變動
                month_ago = [d for d in usd if d.get('date', '') <= (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')]
                change_1m = 0
                if month_ago:
                    old_rate = month_ago[-1].get('spot_buy', month_ago[-1].get('cash_buy', month_ago[-1].get('rate', rate)))
                    change_1m = rate - old_rate if rate and old_rate else 0

                result = {
                    'date': latest.get('date', ''),
                    'usd_twd': rate,
                    'change_1m': round(change_1m, 4) if change_1m else None,
                }
                self._save_indicator('exchange_rate', result)
                return result

        return local.get('data') if local else None

    def _get_cpi(self) -> Optional[Dict]:
        """消費者物價指數"""
        local = self.db.macro_indicators.find_one(
            {'indicator': 'cpi'},
            sort=[('date', -1)]
        )
        if local and self._is_fresh(local, days=30):
            return local.get('data')

        data = self._finmind_fetch('GovernmentBondsYield', days=365)
        # FinMind 可能沒有直接的 CPI，用其他來源
        # 先回傳本地資料
        return local.get('data') if local else {'yoy': None, 'note': '需手動更新'}

    def _get_money_supply(self) -> Optional[Dict]:
        """M1B/M2 貨幣供給"""
        local = self.db.macro_indicators.find_one(
            {'indicator': 'money_supply'},
            sort=[('date', -1)]
        )
        if local and self._is_fresh(local, days=30):
            return local.get('data')

        data = self._finmind_fetch('TaiwanMoneySupply', days=365)
        if data:
            latest = data[-1]
            result = {
                'date': latest.get('date', ''),
                'm1b': latest.get('M1B', latest.get('m1b')),
                'm2': latest.get('M2', latest.get('m2')),
                'm1b_yoy': latest.get('M1B_YoY', latest.get('m1b_yoy')),
                'm2_yoy': latest.get('M2_YoY', latest.get('m2_yoy')),
            }
            self._save_indicator('money_supply', result)
            return result

        return local.get('data') if local else None

    def _get_leading_indicator(self) -> Optional[Dict]:
        """景氣領先指標/燈號"""
        local = self.db.macro_indicators.find_one(
            {'indicator': 'leading'},
            sort=[('date', -1)]
        )
        if local and self._is_fresh(local, days=30):
            return local.get('data')

        return local.get('data') if local else None

    def _get_taiex_summary(self) -> Optional[Dict]:
        """大盤摘要（從本地 stock_price + institutional_flow）"""
        from bson.decimal128 import Decimal128

        def to_f(v):
            if isinstance(v, Decimal128):
                return float(v.to_decimal())
            try:
                return float(v)
            except:
                return None

        # 大盤近期（用 0050 代替）
        prices = list(self.db.stock_price.find(
            {'symbol': '0050'},
            {'date': 1, 'close': 1}
        ).sort('date', -1).limit(22))

        if len(prices) < 2:
            return None

        latest_price = to_f(prices[0]['close'])
        prev_price = to_f(prices[1]['close'])
        price_20d_ago = to_f(prices[-1]['close']) if len(prices) > 20 else prev_price

        daily_change = (latest_price - prev_price) / prev_price * 100 if prev_price else 0
        monthly_change = (latest_price - price_20d_ago) / price_20d_ago * 100 if price_20d_ago else 0

        # 外資近5日買賣超
        cutoff = datetime.now() - timedelta(days=10)
        flows = list(self.db.institutional_flow.find(
            {'date': {'$gte': cutoff}},
            {'foreign_net': 1}
        ).sort('date', -1).limit(5 * 1200))

        foreign_5d = sum(to_f(f.get('foreign_net', 0)) or 0 for f in flows)

        return {
            'date': str(prices[0]['date'])[:10],
            'etf_0050': latest_price,
            'daily_change': round(daily_change, 2),
            'monthly_change': round(monthly_change, 2),
            'foreign_net_5d': round(foreign_5d),
        }

    # ──────────────────────────────────────────────
    #  輔助
    # ──────────────────────────────────────────────
    def _finmind_fetch(self, dataset: str, days: int = 365) -> List[Dict]:
        if not self.finmind_token:
            return []
        try:
            start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            r = requests.get(FINMIND_URL, params={
                'dataset': dataset,
                'start_date': start,
                'token': self.finmind_token,
            }, timeout=15)
            if r.status_code == 200:
                return r.json().get('data', [])
        except Exception as e:
            logger.warning(f'FinMind {dataset} 取得失敗: {e}')
        return []

    def _save_indicator(self, indicator: str, data: Dict):
        self.db.macro_indicators.update_one(
            {'indicator': indicator, 'date': data.get('date', '')},
            {'$set': {'indicator': indicator, 'data': data,
                      'date': data.get('date', ''),
                      'updated_at': datetime.now()}},
            upsert=True
        )

    def _is_fresh(self, doc: Dict, days: int = 7) -> bool:
        updated = doc.get('updated_at')
        if not updated:
            return False
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return (datetime.now() - updated).days < days


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    ma = MacroAnalyzer()

    print(f"\n{'='*55}")
    print("  總經指標總覽")
    print(f"{'='*55}")

    o = ma.overview()
    if o.get('interest_rate') and o['interest_rate'].get('discount_rate'):
        print(f"  重貼現率: {o['interest_rate']['discount_rate']}%")
    if o.get('exchange_rate') and o['exchange_rate'].get('usd_twd'):
        fx = o['exchange_rate']
        print(f"  USD/TWD: {fx['usd_twd']} (月變 {fx.get('change_1m', 'N/A')})")
    if o.get('money_supply') and o['money_supply'].get('m1b_yoy') is not None:
        ms = o['money_supply']
        print(f"  M1B YoY: {ms['m1b_yoy']}%  M2 YoY: {ms['m2_yoy']}%")
    if o.get('taiex'):
        t = o['taiex']
        print(f"  0050: {t['etf_0050']} (日{t['daily_change']:+.2f}% 月{t['monthly_change']:+.2f}%)")
        print(f"  外資近5日: {t['foreign_net_5d']/1e8:.1f}億")

    print(f"\n{'='*55}")
    print("  大盤方向判斷")
    print(f"{'='*55}")
    sig = ma.market_signal()
    print(f"  評分: {sig['score']:+.1f}  {sig['verdict']}")
    print(f"  看多: {sig['bullish_count']}  看空: {sig['bearish_count']}")
    for s in sig['signals']:
        icon = '🟢' if s['direction'] == 'bullish' else ('🔴' if s['direction'] == 'bearish' else '⚪')
        print(f"  {icon} {s['name']}: {s['detail']}")
