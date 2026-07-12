#!/usr/bin/env python3
"""
投資組合追蹤模組
===============
實際持倉即時損益、再平衡建議、股利追蹤/稅務計算、績效歸因分析。

Usage:
    from src.portfolio.tracker import PortfolioTracker
    pt = PortfolioTracker()
    pt.buy('2330', lots=2, price=1850, date='2026-01-15')
    pt.buy('0056', lots=5, price=38, date='2026-02-01')
    print(pt.summary())
    print(pt.rebalance_suggestion({'2330': 60, '0056': 40}))
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import numpy as np
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

COLLECTION = 'portfolio_positions'
TRADE_LOG = 'portfolio_trades'
DIVIDEND_LOG = 'portfolio_dividends'


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class PortfolioTracker:
    """投資組合追蹤器"""

    # 台股交易成本
    COMMISSION_RATE = 0.001425  # 券商手續費 0.1425%
    COMMISSION_DISCOUNT = 0.6  # 手續費折扣（常見 6 折）
    TAX_RATE = 0.003           # 證交稅 0.3%（賣出時）
    ETF_TAX_RATE = 0.001       # ETF 證交稅 0.1%
    DIVIDEND_TAX_RATE = 0.0    # 股利所得（併入綜所稅或分離課稅 28%）

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis",
                 portfolio_name: str = "default"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.portfolio_name = portfolio_name
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.db[COLLECTION].create_index(
            [('portfolio', 1), ('symbol', 1)], unique=True)
        self.db[TRADE_LOG].create_index(
            [('portfolio', 1), ('date', -1)])
        self.db[DIVIDEND_LOG].create_index(
            [('portfolio', 1), ('symbol', 1), ('date', -1)])

    # ──────────────────────────────────────────────
    #  交易操作
    # ──────────────────────────────────────────────
    def buy(self, symbol: str, lots: int = 0, shares: int = 0,
            price: float = None, date: str = None, note: str = ''):
        """買入"""
        if lots > 0:
            shares = lots * 1000
        if shares <= 0:
            raise ValueError('需指定 lots 或 shares')
        if price is None:
            price = self._get_latest_price(symbol)
        if price is None:
            raise ValueError(f'無法取得 {symbol} 股價')

        trade_date = self._parse_date(date)
        cost = shares * price
        commission = cost * self.COMMISSION_RATE * self.COMMISSION_DISCOUNT
        total_cost = cost + commission

        # 更新持倉
        pos = self._get_position(symbol)
        if pos:
            # 加碼：計算加權平均成本
            old_shares = pos['shares']
            old_avg = pos['avg_cost']
            new_shares = old_shares + shares
            new_avg = (old_shares * old_avg + shares * price) / new_shares
            self.db[COLLECTION].update_one(
                {'portfolio': self.portfolio_name, 'symbol': symbol},
                {'$set': {
                    'shares': new_shares,
                    'avg_cost': round(new_avg, 4),
                    'total_cost': round(new_shares * new_avg, 2),
                    'updated_at': datetime.now(timezone.utc),
                }}
            )
        else:
            self.db[COLLECTION].insert_one({
                'portfolio': self.portfolio_name,
                'symbol': symbol,
                'shares': shares,
                'avg_cost': price,
                'total_cost': round(total_cost, 2),
                'first_buy_date': trade_date,
                'updated_at': datetime.now(timezone.utc),
            })

        # 記錄交易
        self.db[TRADE_LOG].insert_one({
            'portfolio': self.portfolio_name,
            'symbol': symbol,
            'action': 'BUY',
            'shares': shares,
            'price': price,
            'cost': round(cost, 2),
            'commission': round(commission, 2),
            'total': round(total_cost, 2),
            'date': trade_date,
            'note': note,
            'created_at': datetime.now(timezone.utc),
        })

        logger.info(f'買入 {symbol} {shares}股 @ {price} = ${total_cost:,.0f}')

    def sell(self, symbol: str, lots: int = 0, shares: int = 0,
             price: float = None, date: str = None, note: str = ''):
        """賣出"""
        if lots > 0:
            shares = lots * 1000
        if shares <= 0:
            raise ValueError('需指定 lots 或 shares')
        if price is None:
            price = self._get_latest_price(symbol)

        pos = self._get_position(symbol)
        if not pos or pos['shares'] < shares:
            raise ValueError(f'{symbol} 持股不足 (持有 {pos["shares"] if pos else 0})')

        trade_date = self._parse_date(date)
        revenue = shares * price
        commission = revenue * self.COMMISSION_RATE * self.COMMISSION_DISCOUNT

        # 判斷 ETF 或一般股票稅率
        is_etf = symbol.startswith('00') or symbol.startswith('0')
        tax = revenue * (self.ETF_TAX_RATE if is_etf else self.TAX_RATE)
        net_revenue = revenue - commission - tax

        # 計算已實現損益
        cost_basis = shares * pos['avg_cost']
        realized_pnl = net_revenue - cost_basis

        # 更新持倉
        remaining = pos['shares'] - shares
        if remaining > 0:
            self.db[COLLECTION].update_one(
                {'portfolio': self.portfolio_name, 'symbol': symbol},
                {'$set': {
                    'shares': remaining,
                    'total_cost': round(remaining * pos['avg_cost'], 2),
                    'updated_at': datetime.now(timezone.utc),
                }}
            )
        else:
            self.db[COLLECTION].delete_one(
                {'portfolio': self.portfolio_name, 'symbol': symbol})

        # 記錄交易
        self.db[TRADE_LOG].insert_one({
            'portfolio': self.portfolio_name,
            'symbol': symbol,
            'action': 'SELL',
            'shares': shares,
            'price': price,
            'revenue': round(revenue, 2),
            'commission': round(commission, 2),
            'tax': round(tax, 2),
            'net_revenue': round(net_revenue, 2),
            'cost_basis': round(cost_basis, 2),
            'realized_pnl': round(realized_pnl, 2),
            'date': trade_date,
            'note': note,
            'created_at': datetime.now(timezone.utc),
        })

        sign = '+' if realized_pnl >= 0 else ''
        logger.info(f'賣出 {symbol} {shares}股 @ {price} 損益: {sign}${realized_pnl:,.0f}')

    def record_dividend(self, symbol: str, cash_per_share: float,
                        stock_per_share: float = 0, ex_date: str = None,
                        pay_date: str = None):
        """記錄股利"""
        pos = self._get_position(symbol)
        if not pos:
            logger.warning(f'{symbol} 非持有股票')
            return

        shares = pos['shares']
        cash_total = shares * cash_per_share
        stock_shares = int(shares * stock_per_share / 10) if stock_per_share else 0

        # 股利所得稅計算（可選擇合併或分離課稅 28%）
        tax_combined = cash_total  # 併入綜所稅（依個人稅率）
        tax_separated = cash_total * 0.28  # 分離課稅 28%
        tax_credit = min(cash_total * 0.087, 80000)  # 可抵減稅額 8.5%，上限 8 萬

        self.db[DIVIDEND_LOG].insert_one({
            'portfolio': self.portfolio_name,
            'symbol': symbol,
            'shares': shares,
            'cash_per_share': cash_per_share,
            'stock_per_share': stock_per_share,
            'cash_total': round(cash_total, 2),
            'stock_shares': stock_shares,
            'tax_separated_28pct': round(tax_separated, 2),
            'tax_credit_8_5pct': round(tax_credit, 2),
            'ex_date': ex_date,
            'pay_date': pay_date,
            'created_at': datetime.now(timezone.utc),
        })

        # 若有股票股利，增加持股
        if stock_shares > 0:
            new_shares = pos['shares'] + stock_shares
            new_avg = pos['avg_cost'] * pos['shares'] / new_shares
            self.db[COLLECTION].update_one(
                {'portfolio': self.portfolio_name, 'symbol': symbol},
                {'$set': {
                    'shares': new_shares,
                    'avg_cost': round(new_avg, 4),
                    'updated_at': datetime.now(timezone.utc),
                }}
            )

        logger.info(f'{symbol} 股利: 現金 ${cash_total:,.0f}'
                    + (f' + 股票 {stock_shares} 股' if stock_shares else ''))

    # ──────────────────────────────────────────────
    #  持倉損益
    # ──────────────────────────────────────────────
    def summary(self) -> Dict:
        """投資組合即時損益摘要"""
        positions = list(self.db[COLLECTION].find(
            {'portfolio': self.portfolio_name}))

        if not positions:
            return {'portfolio': self.portfolio_name, 'positions': [], 'total': {}}

        holdings = []
        total_cost = 0
        total_market = 0
        total_pnl = 0
        total_dividend = 0

        for pos in positions:
            sym = pos['symbol']
            shares = pos['shares']
            avg_cost = pos['avg_cost']
            cost = shares * avg_cost

            market_price = self._get_latest_price(sym)
            if market_price is None:
                market_price = avg_cost

            market_value = shares * market_price
            unrealized_pnl = market_value - cost
            pnl_pct = (unrealized_pnl / cost * 100) if cost > 0 else 0

            # 累計股利
            div_total = self._total_dividends(sym)

            name = self._get_stock_name(sym)

            holdings.append({
                'symbol': sym,
                'name': name,
                'shares': shares,
                'lots': shares // 1000,
                'avg_cost': round(avg_cost, 2),
                'market_price': round(market_price, 2),
                'cost': round(cost),
                'market_value': round(market_value),
                'unrealized_pnl': round(unrealized_pnl),
                'pnl_pct': round(pnl_pct, 2),
                'weight': 0,  # 下面計算
                'dividends_received': round(div_total),
                'total_return': round(unrealized_pnl + div_total),
                'total_return_pct': round((unrealized_pnl + div_total) / cost * 100, 2) if cost > 0 else 0,
            })

            total_cost += cost
            total_market += market_value
            total_pnl += unrealized_pnl
            total_dividend += div_total

        # 計算權重
        for h in holdings:
            h['weight'] = round(h['market_value'] / total_market * 100, 1) if total_market > 0 else 0

        # 已實現損益
        realized = self._total_realized_pnl()

        holdings.sort(key=lambda x: x['market_value'], reverse=True)

        return {
            'portfolio': self.portfolio_name,
            'positions': holdings,
            'total': {
                'positions_count': len(holdings),
                'total_cost': round(total_cost),
                'total_market_value': round(total_market),
                'unrealized_pnl': round(total_pnl),
                'unrealized_pnl_pct': round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
                'realized_pnl': round(realized),
                'dividends_received': round(total_dividend),
                'total_return': round(total_pnl + realized + total_dividend),
            },
            'updated_at': datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────
    #  再平衡建議
    # ──────────────────────────────────────────────
    def rebalance_suggestion(self, target_weights: Dict[str, float],
                             tolerance: float = 5.0) -> Dict:
        """
        再平衡建議
        target_weights: {'2330': 50, '0056': 30, '2317': 20}（百分比）
        tolerance: 偏離容忍度（預設 5%）
        """
        s = self.summary()
        if not s['positions']:
            return {'error': '無持倉'}

        total_value = s['total']['total_market_value']
        current_weights = {h['symbol']: h['weight'] for h in s['positions']}

        actions = []
        for sym, target_pct in target_weights.items():
            current_pct = current_weights.get(sym, 0)
            diff = target_pct - current_pct

            if abs(diff) <= tolerance:
                actions.append({
                    'symbol': sym,
                    'current_weight': current_pct,
                    'target_weight': target_pct,
                    'diff': round(diff, 1),
                    'action': '維持',
                    'amount': 0,
                })
                continue

            target_value = total_value * target_pct / 100
            current_value = total_value * current_pct / 100
            diff_value = target_value - current_value
            price = self._get_latest_price(sym) or 1

            lots = int(abs(diff_value) / (price * 1000))
            action = '買入' if diff > 0 else '賣出'

            actions.append({
                'symbol': sym,
                'name': self._get_stock_name(sym),
                'current_weight': current_pct,
                'target_weight': target_pct,
                'diff': round(diff, 1),
                'action': action,
                'lots': lots,
                'amount': round(abs(diff_value)),
                'price': price,
            })

        # 找不在目標但有持倉的
        for sym in current_weights:
            if sym not in target_weights:
                h = next((x for x in s['positions'] if x['symbol'] == sym), None)
                if h:
                    actions.append({
                        'symbol': sym,
                        'name': h['name'],
                        'current_weight': h['weight'],
                        'target_weight': 0,
                        'diff': -h['weight'],
                        'action': '全部賣出',
                        'lots': h['lots'],
                        'amount': h['market_value'],
                    })

        actions.sort(key=lambda x: abs(x['diff']), reverse=True)

        return {
            'total_value': total_value,
            'tolerance': tolerance,
            'actions': actions,
        }

    # ──────────────────────────────────────────────
    #  股利追蹤 / 稅務
    # ──────────────────────────────────────────────
    def dividend_summary(self, year: int = None) -> Dict:
        """股利收入摘要與稅務計算"""
        query = {'portfolio': self.portfolio_name}
        if year:
            query['ex_date'] = {'$regex': f'^{year}'}

        records = list(self.db[DIVIDEND_LOG].find(query).sort('ex_date', -1))

        by_symbol = defaultdict(lambda: {'cash': 0, 'stock_shares': 0, 'count': 0})
        total_cash = 0
        total_stock_shares = 0

        for r in records:
            sym = r['symbol']
            cash = r.get('cash_total', 0)
            stock = r.get('stock_shares', 0)
            by_symbol[sym]['cash'] += cash
            by_symbol[sym]['stock_shares'] += stock
            by_symbol[sym]['count'] += 1
            total_cash += cash
            total_stock_shares += stock

        # 稅務試算
        tax_separated = total_cash * 0.28
        tax_credit = min(total_cash * 0.087, 80000)

        return {
            'year': year or '全部',
            'total_cash_dividend': round(total_cash),
            'total_stock_shares': total_stock_shares,
            'by_symbol': {sym: {
                'cash': round(v['cash']),
                'stock_shares': v['stock_shares'],
                'count': v['count'],
            } for sym, v in by_symbol.items()},
            'tax': {
                'separated_28pct': round(tax_separated),
                'credit_8_5pct': round(tax_credit),
                'net_after_separated': round(total_cash - tax_separated),
                'note': '分離課稅 28% vs 合併申報（8.5% 可抵減，上限 8 萬）',
            },
            'records_count': len(records),
        }

    # ──────────────────────────────────────────────
    #  績效歸因分析
    # ──────────────────────────────────────────────
    def performance_attribution(self, benchmark: str = '0050') -> Dict:
        """
        Brinson 績效歸因（簡化版）
        分解投組報酬為：選股效果 + 配置效果 + 交互效果
        """
        s = self.summary()
        if not s['positions']:
            return {'error': '無持倉'}

        # 取各持股與大盤近期報酬
        holdings = s['positions']
        total_value = s['total']['total_market_value']

        # 大盤報酬（用 0050 近 1 個月）
        bm_ret = self._calc_period_return(benchmark, days=30)
        if bm_ret is None:
            bm_ret = 0

        # 各持股報酬
        stock_contributions = []
        portfolio_return = 0

        for h in holdings:
            sym = h['symbol']
            weight = h['weight'] / 100
            stock_ret = self._calc_period_return(sym, days=30)
            if stock_ret is None:
                stock_ret = 0

            # 選股效果 = 權重 × (個股報酬 - 大盤報酬)
            selection = weight * (stock_ret - bm_ret)
            # 配置效果 = (權重 - 等權) × (大盤報酬)
            equal_weight = 1 / len(holdings)
            allocation = (weight - equal_weight) * bm_ret
            # 個股貢獻
            contribution = weight * stock_ret

            portfolio_return += contribution

            stock_contributions.append({
                'symbol': sym,
                'name': h['name'],
                'weight': round(weight * 100, 1),
                'stock_return': round(stock_ret * 100, 2),
                'contribution': round(contribution * 100, 3),
                'selection_effect': round(selection * 100, 3),
                'allocation_effect': round(allocation * 100, 3),
            })

        # 超額報酬
        excess_return = portfolio_return - bm_ret

        stock_contributions.sort(key=lambda x: x['contribution'], reverse=True)

        return {
            'period': '近1個月',
            'portfolio_return': round(portfolio_return * 100, 2),
            'benchmark_return': round(bm_ret * 100, 2),
            'excess_return': round(excess_return * 100, 2),
            'benchmark': benchmark,
            'stock_contributions': stock_contributions,
            'top_contributor': stock_contributions[0]['symbol'] if stock_contributions else None,
            'worst_contributor': stock_contributions[-1]['symbol'] if stock_contributions else None,
        }

    # ──────────────────────────────────────────────
    #  交易歷史
    # ──────────────────────────────────────────────
    def trade_history(self, limit: int = 20) -> List[Dict]:
        trades = list(self.db[TRADE_LOG].find(
            {'portfolio': self.portfolio_name},
            {'_id': 0}
        ).sort('date', -1).limit(limit))
        return trades

    # ──────────────────────────────────────────────
    #  輔助方法
    # ──────────────────────────────────────────────
    def _get_position(self, symbol: str) -> Optional[Dict]:
        return self.db[COLLECTION].find_one(
            {'portfolio': self.portfolio_name, 'symbol': symbol})

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

    def _parse_date(self, date_str: str = None) -> str:
        if date_str:
            return date_str
        return datetime.now().strftime('%Y-%m-%d')

    def _total_dividends(self, symbol: str) -> float:
        pipeline = [
            {'$match': {'portfolio': self.portfolio_name, 'symbol': symbol}},
            {'$group': {'_id': None, 'total': {'$sum': '$cash_total'}}},
        ]
        result = list(self.db[DIVIDEND_LOG].aggregate(pipeline))
        return result[0]['total'] if result else 0

    def _total_realized_pnl(self) -> float:
        pipeline = [
            {'$match': {'portfolio': self.portfolio_name, 'action': 'SELL'}},
            {'$group': {'_id': None, 'total': {'$sum': '$realized_pnl'}}},
        ]
        result = list(self.db[TRADE_LOG].aggregate(pipeline))
        return result[0]['total'] if result else 0

    def _calc_period_return(self, symbol: str, days: int = 30) -> Optional[float]:
        cutoff = datetime.now() - timedelta(days=days)
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'close': 1, 'date': 1}
        ).sort('date', 1))

        if len(prices) < 2:
            return None

        p0 = _to_float(prices[0]['close'])
        p1 = _to_float(prices[-1]['close'])
        if p0 and p1 and p0 > 0:
            return (p1 - p0) / p0
        return None


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    pt = PortfolioTracker(portfolio_name='test_demo')

    # 清除測試資料
    pt.db[COLLECTION].delete_many({'portfolio': 'test_demo'})
    pt.db[TRADE_LOG].delete_many({'portfolio': 'test_demo'})
    pt.db[DIVIDEND_LOG].delete_many({'portfolio': 'test_demo'})

    # 模擬交易
    pt.buy('2330', lots=1, price=1800, date='2026-01-15', note='初始建倉')
    pt.buy('0056', lots=10, price=37, date='2026-01-20', note='高殖利率 ETF')
    pt.buy('2317', lots=5, price=195, date='2026-02-01', note='鴻海')
    pt.buy('2330', lots=1, price=1750, date='2026-02-10', note='加碼')

    # 記錄股利
    pt.record_dividend('0056', cash_per_share=0.79, ex_date='2026-01-16')

    # 損益摘要
    print(f"\n{'='*65}")
    print("  投資組合即時損益")
    print(f"{'='*65}")
    s = pt.summary()
    print(f"\n  {'股票':<6} {'名稱':<8} {'張數':>4} {'成本':>8} {'市值':>8} {'損益':>8} {'報酬':>7} {'權重':>5}")
    print(f"  {'-'*60}")
    for h in s['positions']:
        sign = '+' if h['unrealized_pnl'] >= 0 else ''
        print(f"  {h['symbol']:<6} {h['name']:<8} {h['lots']:>4} "
              f"{h['cost']:>8,} {h['market_value']:>8,} "
              f"{sign}{h['unrealized_pnl']:>7,} {h['pnl_pct']:>+6.1f}% {h['weight']:>4.1f}%")

    t = s['total']
    print(f"  {'-'*60}")
    print(f"  {'合計':<15} {t['total_cost']:>12,} {t['total_market_value']:>8,} "
          f"{t['unrealized_pnl']:>+8,} {t['unrealized_pnl_pct']:>+6.1f}%")
    print(f"  已實現損益: ${t['realized_pnl']:,}  股利: ${t['dividends_received']:,}")

    # 再平衡建議
    print(f"\n{'='*65}")
    print("  再平衡建議 (目標: 2330=50%, 0056=30%, 2317=20%)")
    print(f"{'='*65}")
    rb = pt.rebalance_suggestion({'2330': 50, '0056': 30, '2317': 20})
    for a in rb['actions']:
        print(f"  {a['symbol']:<6} 現:{a['current_weight']:>5.1f}% → 目標:{a['target_weight']:>5.1f}%  "
              f"差:{a['diff']:>+5.1f}%  {a['action']} {a.get('lots','')} 張")

    # 股利摘要
    print(f"\n{'='*65}")
    print("  股利追蹤")
    div = pt.dividend_summary()
    print(f"  現金股利合計: ${div['total_cash_dividend']:,}")
    print(f"  分離課稅(28%): ${div['tax']['separated_28pct']:,}  "
          f"可抵減(8.5%): ${div['tax']['credit_8_5pct']:,}")

    # 績效歸因
    print(f"\n{'='*65}")
    print("  績效歸因分析")
    print(f"{'='*65}")
    attr = pt.performance_attribution()
    if not attr.get('error'):
        print(f"  投組報酬: {attr['portfolio_return']:+.2f}%  "
              f"大盤(0050): {attr['benchmark_return']:+.2f}%  "
              f"超額: {attr['excess_return']:+.2f}%")
        print(f"\n  {'股票':<6} {'權重':>5} {'報酬':>7} {'貢獻':>7} {'選股':>7}")
        for c in attr['stock_contributions']:
            print(f"  {c['symbol']:<6} {c['weight']:>4.1f}% {c['stock_return']:>+6.2f}% "
                  f"{c['contribution']:>+6.3f}% {c['selection_effect']:>+6.3f}%")

    # 清除測試資料
    pt.db[COLLECTION].delete_many({'portfolio': 'test_demo'})
    pt.db[TRADE_LOG].delete_many({'portfolio': 'test_demo'})
    pt.db[DIVIDEND_LOG].delete_many({'portfolio': 'test_demo'})
