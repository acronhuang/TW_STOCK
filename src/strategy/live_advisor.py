#!/usr/bin/env python3
"""
回測策略→實盤交易建議→投組追蹤 串接模組
=======================================
將回測驗證過的策略轉化為實盤交易建議，並自動記錄到投資組合。

Usage:
    from src.strategy.live_advisor import LiveAdvisor
    la = LiveAdvisor(capital=5_000_000)
    suggestions = la.generate_suggestions()  # 產生交易建議
    la.execute(suggestions)                  # 執行到投組（需確認）
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


class LiveAdvisor:
    """策略→交易建議→投組串接"""

    def __init__(self,
                 capital: float = 5_000_000,
                 max_positions: int = 10,
                 max_position_pct: float = 0.15,
                 stop_loss_pct: float = 0.08,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis",
                 portfolio_name: str = "live"):
        self.capital = capital
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.portfolio_name = portfolio_name

    def generate_suggestions(self) -> Dict:
        """產生交易建議（買入 + 賣出）"""
        buy_candidates = self._screen_buy_candidates()
        sell_candidates = self._screen_sell_candidates()
        rebalance = self._check_rebalance()

        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'capital': self.capital,
            'buy': buy_candidates,
            'sell': sell_candidates,
            'rebalance': rebalance,
            'summary': {
                'buy_count': len(buy_candidates),
                'sell_count': len(sell_candidates),
                'rebalance_count': len(rebalance),
            },
        }

    def execute(self, suggestions: Dict, confirm: bool = False):
        """執行交易建議到投組（需 confirm=True）"""
        if not confirm:
            logger.warning('未確認執行，請設定 confirm=True')
            return

        from src.portfolio.tracker import PortfolioTracker
        pt = PortfolioTracker(portfolio_name=self.portfolio_name)

        for sell in suggestions.get('sell', []):
            try:
                pt.sell(sell['symbol'], lots=sell['lots'],
                        price=sell['price'], note=sell['reason'])
                logger.info(f"賣出 {sell['symbol']} {sell['lots']}張")
            except Exception as e:
                logger.error(f"賣出 {sell['symbol']} 失敗: {e}")

        for buy in suggestions.get('buy', []):
            try:
                pt.buy(buy['symbol'], lots=buy['lots'],
                       price=buy['price'], note=buy['reason'])
                logger.info(f"買入 {buy['symbol']} {buy['lots']}張")
            except Exception as e:
                logger.error(f"買入 {buy['symbol']} 失敗: {e}")

    # ──────────────────────────────────────────────
    #  買入篩選
    # ──────────────────────────────────────────────
    def _screen_buy_candidates(self) -> List[Dict]:
        """用綜合選股評分 + 風險管理篩選買入標的"""
        from src.analysis.stock_ranker import StockRanker
        sr = StockRanker()
        top_stocks = sr.rank(limit=50, min_pe=1, max_pe=50)

        # 已持有的股票
        held = self._get_held_symbols()
        current_positions = len(held)
        available_slots = self.max_positions - current_positions
        if available_slots <= 0:
            return []

        # 計算可用資金
        total_held_value = self._get_total_held_value()
        available_capital = self.capital - total_held_value

        candidates = []
        for stock in top_stocks:
            sym = stock['symbol']
            if sym in held:
                continue

            price = stock.get('price')
            if not price or price <= 0:
                continue

            # 部位大小（上限 15% 總資金）
            max_value = self.capital * self.max_position_pct
            position_value = min(available_capital / available_slots, max_value)
            lots = int(position_value / (price * 1000))

            if lots <= 0:
                continue

            score = stock['total_score']
            if score < 65:  # 只推薦 B+ 以上
                continue

            # 額外條件：RSI 不能超買
            rsi = stock.get('metrics', {}).get('rsi_14')
            if rsi and rsi > 75:
                continue

            candidates.append({
                'symbol': sym,
                'name': stock['name'],
                'price': price,
                'lots': lots,
                'value': lots * 1000 * price,
                'score': score,
                'grade': stock['grade'],
                'stop_loss': round(price * (1 - self.stop_loss_pct), 2),
                'reason': f"綜合評分 {score:.1f} {stock['grade']}",
                'scores': stock.get('scores', {}),
            })

            if len(candidates) >= available_slots:
                break

        return candidates

    # ──────────────────────────────────────────────
    #  賣出篩選
    # ──────────────────────────────────────────────
    def _screen_sell_candidates(self) -> List[Dict]:
        """檢查持倉是否需要停損或獲利了結"""
        from src.portfolio.tracker import PortfolioTracker, COLLECTION
        positions = list(self.db[COLLECTION].find(
            {'portfolio': self.portfolio_name}))

        sells = []
        for pos in positions:
            sym = pos['symbol']
            avg_cost = pos['avg_cost']
            shares = pos['shares']
            price = self._get_latest_price(sym)

            if not price:
                continue

            pnl_pct = (price - avg_cost) / avg_cost

            # 停損
            if pnl_pct <= -self.stop_loss_pct:
                sells.append({
                    'symbol': sym,
                    'name': self._get_stock_name(sym),
                    'price': price,
                    'lots': shares // 1000,
                    'avg_cost': round(avg_cost, 2),
                    'pnl_pct': round(pnl_pct * 100, 2),
                    'reason': f'停損（虧損 {pnl_pct*100:.1f}%，超過 -{self.stop_loss_pct*100:.0f}%）',
                    'action': 'stop_loss',
                })
                continue

            # RSI 超買 + 獲利
            factor = self.db.stock_factors.find_one(
                {'symbol': sym, 'rsi_14': {'$ne': None}},
                {'rsi_14': 1}, sort=[('date', -1)]
            )
            rsi = _to_float(factor.get('rsi_14')) if factor else None

            if rsi and rsi > 80 and pnl_pct > 0.10:
                sells.append({
                    'symbol': sym,
                    'name': self._get_stock_name(sym),
                    'price': price,
                    'lots': shares // 1000 // 2,  # 賣一半
                    'avg_cost': round(avg_cost, 2),
                    'pnl_pct': round(pnl_pct * 100, 2),
                    'reason': f'RSI 超買({rsi:.0f}) + 獲利({pnl_pct*100:.1f}%)，建議減碼50%',
                    'action': 'take_profit',
                })

        return sells

    # ──────────────────────────────────────────────
    #  再平衡檢查
    # ──────────────────────────────────────────────
    def _check_rebalance(self) -> List[Dict]:
        """檢查持倉是否偏離目標權重過多"""
        from src.portfolio.tracker import COLLECTION
        positions = list(self.db[COLLECTION].find(
            {'portfolio': self.portfolio_name}))

        if not positions:
            return []

        total_value = 0
        pos_data = []
        for pos in positions:
            price = self._get_latest_price(pos['symbol'])
            if price:
                value = pos['shares'] * price
                total_value += value
                pos_data.append({
                    'symbol': pos['symbol'],
                    'value': value,
                    'shares': pos['shares'],
                    'price': price,
                })

        if total_value == 0:
            return []

        alerts = []
        target_pct = 100 / len(pos_data) if pos_data else 100
        tolerance = 10  # 10% 偏離容忍

        for p in pos_data:
            actual_pct = p['value'] / total_value * 100
            diff = actual_pct - target_pct

            if abs(diff) > tolerance:
                action = '減碼' if diff > 0 else '加碼'
                alerts.append({
                    'symbol': p['symbol'],
                    'name': self._get_stock_name(p['symbol']),
                    'current_pct': round(actual_pct, 1),
                    'target_pct': round(target_pct, 1),
                    'diff': round(diff, 1),
                    'action': action,
                    'reason': f'權重偏離 {diff:+.1f}%（容忍 ±{tolerance}%）',
                })

        return alerts

    # ──────────────────────────────────────────────
    #  輔助
    # ──────────────────────────────────────────────
    def _get_held_symbols(self) -> set:
        from src.portfolio.tracker import COLLECTION
        return set(p['symbol'] for p in self.db[COLLECTION].find(
            {'portfolio': self.portfolio_name}, {'symbol': 1}))

    def _get_total_held_value(self) -> float:
        from src.portfolio.tracker import COLLECTION
        total = 0
        for pos in self.db[COLLECTION].find({'portfolio': self.portfolio_name}):
            price = self._get_latest_price(pos['symbol'])
            if price:
                total += pos['shares'] * price
        return total

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
        return ''


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    la = LiveAdvisor(capital=5_000_000)

    print(f"\n{'='*70}")
    print("  策略交易建議（資金 500 萬）")
    print(f"{'='*70}")

    suggestions = la.generate_suggestions()

    if suggestions['buy']:
        print(f"\n  📈 買入建議 ({len(suggestions['buy'])} 支):")
        for b in suggestions['buy']:
            print(f"    {b['symbol']} {b['name']} @ {b['price']:.1f}  "
                  f"{b['lots']}張 (${b['value']:,.0f})  "
                  f"停損:{b['stop_loss']}  {b['reason']}")
    else:
        print('\n  📈 無買入建議')

    if suggestions['sell']:
        print(f"\n  📉 賣出建議 ({len(suggestions['sell'])} 支):")
        for s in suggestions['sell']:
            print(f"    {s['symbol']} {s['name']} @ {s['price']:.1f}  "
                  f"{s['lots']}張  {s['reason']}")
    else:
        print('\n  📉 無賣出建議（無持倉或無需調整）')

    if suggestions['rebalance']:
        print(f"\n  ⚖️ 再平衡建議:")
        for r in suggestions['rebalance']:
            print(f"    {r['symbol']} {r['action']}: {r['reason']}")
