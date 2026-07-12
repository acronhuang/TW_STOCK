#!/usr/bin/env python3
"""
風險管理模組：VaR + CVaR + 部位管理 + Kelly Criterion
====================================================
提供個股與投資組合層級的風險度量與部位建議。

Usage:
    from src.analysis.risk_manager import RiskAnalyzer
    ra = RiskAnalyzer()
    risk = ra.analyze('2330')
    portfolio = ra.portfolio_risk(['2330', '2317', '2454'], weights=[0.5, 0.3, 0.2])
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from scipy import stats as sp_stats
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


class RiskAnalyzer:
    """個股與投資組合風險分析"""

    RISK_FREE_RATE = 0.015  # 台灣十年期公債
    TRADING_DAYS = 250

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    # ──────────────────────────────────────────────
    #  個股風險分析
    # ──────────────────────────────────────────────
    def analyze(self, symbol: str, lookback_days: int = 252) -> Dict:
        """完整個股風險分析"""
        returns = self._get_returns(symbol, lookback_days)
        if returns is None or len(returns) < 30:
            return {'symbol': symbol, 'error': '價格資料不足'}

        price = self._get_latest_price(symbol)
        arr = np.array(returns)

        # 基本統計
        daily_mean = float(np.mean(arr))
        daily_std = float(np.std(arr, ddof=1))
        annual_return = daily_mean * self.TRADING_DAYS
        annual_vol = daily_std * np.sqrt(self.TRADING_DAYS)

        # VaR（歷史模擬法）
        var_95 = float(-np.percentile(arr, 5))
        var_99 = float(-np.percentile(arr, 1))

        # CVaR（條件風險值 = Expected Shortfall）
        cvar_95 = float(-np.mean(arr[arr <= np.percentile(arr, 5)]))
        cvar_99 = float(-np.mean(arr[arr <= np.percentile(arr, 1)]))

        # 參數法 VaR（假設常態分佈）
        param_var_95 = float(-(daily_mean + sp_stats.norm.ppf(0.05) * daily_std))
        param_var_99 = float(-(daily_mean + sp_stats.norm.ppf(0.01) * daily_std))

        # 最大回撤
        max_dd, dd_start, dd_end = self._calc_max_drawdown(returns)

        # Sharpe Ratio
        excess_return = annual_return - self.RISK_FREE_RATE
        sharpe = excess_return / annual_vol if annual_vol > 0 else 0

        # Sortino Ratio（只計算下行風險）
        downside_returns = arr[arr < 0]
        downside_std = float(np.std(downside_returns, ddof=1)) * np.sqrt(self.TRADING_DAYS) if len(downside_returns) > 1 else annual_vol
        sortino = excess_return / downside_std if downside_std > 0 else 0

        # Calmar Ratio
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        # Beta（vs 0050 大盤 ETF）
        beta = self._calc_beta(symbol, lookback_days)

        # 偏態與峰態
        skew = float(sp_stats.skew(arr))
        kurtosis = float(sp_stats.kurtosis(arr))

        # Kelly Criterion
        kelly = self._kelly_criterion(arr)

        # 風險等級
        risk_level = self._risk_grade(annual_vol, max_dd, var_95)

        return {
            'symbol': symbol,
            'current_price': price,
            'data_points': len(returns),
            'returns': {
                'daily_mean': round(daily_mean * 100, 4),
                'annual_return': round(annual_return * 100, 2),
                'annual_volatility': round(annual_vol * 100, 2),
            },
            'var': {
                'daily_var_95': round(var_95 * 100, 2),
                'daily_var_99': round(var_99 * 100, 2),
                'param_var_95': round(param_var_95 * 100, 2),
                'param_var_99': round(param_var_99 * 100, 2),
                'annual_var_95': round(var_95 * np.sqrt(self.TRADING_DAYS) * 100, 2),
            },
            'cvar': {
                'daily_cvar_95': round(cvar_95 * 100, 2),
                'daily_cvar_99': round(cvar_99 * 100, 2),
            },
            'drawdown': {
                'max_drawdown': round(max_dd * 100, 2),
                'dd_start_idx': dd_start,
                'dd_end_idx': dd_end,
            },
            'ratios': {
                'sharpe': round(sharpe, 3),
                'sortino': round(sortino, 3),
                'calmar': round(calmar, 3),
                'beta': round(beta, 3),
            },
            'distribution': {
                'skewness': round(skew, 3),
                'kurtosis': round(kurtosis, 3),
            },
            'position_sizing': {
                'kelly_fraction': round(kelly, 4),
                'half_kelly': round(kelly / 2, 4),
                'max_position_pct': round(min(kelly / 2, 0.25) * 100, 1),
            },
            'risk_level': risk_level,
        }

    # ──────────────────────────────────────────────
    #  投資組合風險
    # ──────────────────────────────────────────────
    def portfolio_risk(self, symbols: List[str], weights: List[float] = None,
                       lookback_days: int = 252) -> Dict:
        """投資組合風險分析"""
        n = len(symbols)
        if weights is None:
            weights = [1.0 / n] * n
        weights = np.array(weights)
        weights = weights / weights.sum()

        # 收集報酬率
        all_returns = {}
        for sym in symbols:
            rets = self._get_returns(sym, lookback_days)
            if rets and len(rets) > 30:
                all_returns[sym] = rets

        if len(all_returns) < 2:
            return {'error': '有效資料不足，需至少2支股票'}

        # 對齊長度（取最短的）
        min_len = min(len(r) for r in all_returns.values())
        ret_matrix = np.array([all_returns[sym][-min_len:] for sym in symbols if sym in all_returns])

        if ret_matrix.shape[0] != n:
            return {'error': '部分股票資料缺失'}

        # 相關性矩陣
        corr_matrix = np.corrcoef(ret_matrix)
        cov_matrix = np.cov(ret_matrix) * self.TRADING_DAYS

        # 投組報酬與風險
        port_return = float(np.sum(weights * np.mean(ret_matrix, axis=1) * self.TRADING_DAYS))
        port_vol = float(np.sqrt(weights @ cov_matrix @ weights))

        # 投組 VaR
        port_daily_returns = ret_matrix.T @ weights
        port_var_95 = float(-np.percentile(port_daily_returns, 5))
        port_cvar_95 = float(-np.mean(port_daily_returns[port_daily_returns <= np.percentile(port_daily_returns, 5)]))

        # 投組最大回撤
        max_dd, _, _ = self._calc_max_drawdown(port_daily_returns.tolist())

        # 投組 Sharpe
        sharpe = (port_return - self.RISK_FREE_RATE) / port_vol if port_vol > 0 else 0

        # 個股貢獻
        contributions = []
        marginal_cov = cov_matrix @ weights
        for i, sym in enumerate(symbols):
            risk_contrib = weights[i] * marginal_cov[i] / (port_vol ** 2) if port_vol > 0 else 0
            contributions.append({
                'symbol': sym,
                'weight': round(float(weights[i]) * 100, 1),
                'risk_contribution': round(float(risk_contrib) * 100, 1),
            })

        return {
            'symbols': symbols,
            'weights': {sym: round(float(w) * 100, 1) for sym, w in zip(symbols, weights)},
            'portfolio': {
                'annual_return': round(port_return * 100, 2),
                'annual_volatility': round(port_vol * 100, 2),
                'sharpe': round(sharpe, 3),
                'max_drawdown': round(max_dd * 100, 2),
            },
            'var': {
                'daily_var_95': round(port_var_95 * 100, 2),
                'daily_cvar_95': round(port_cvar_95 * 100, 2),
            },
            'correlation_matrix': {
                'symbols': symbols,
                'matrix': [[round(float(corr_matrix[i][j]), 3) for j in range(n)] for i in range(n)],
            },
            'risk_contributions': contributions,
            'diversification_ratio': round(
                sum(float(weights[i]) * float(np.std(ret_matrix[i]) * np.sqrt(self.TRADING_DAYS))
                    for i in range(n)) / port_vol, 3
            ) if port_vol > 0 else 1.0,
            'data_points': min_len,
        }

    # ──────────────────────────────────────────────
    #  部位管理建議
    # ──────────────────────────────────────────────
    def position_size(self, symbol: str, capital: float,
                      max_loss_pct: float = 0.02, stop_loss_pct: float = 0.08) -> Dict:
        """
        ATR-based 部位管理
        capital: 總資金
        max_loss_pct: 單筆最大虧損佔總資金比例（預設 2%）
        stop_loss_pct: 停損比例（預設 8%）
        """
        price = self._get_latest_price(symbol)
        if price is None:
            return {'error': '無法取得股價'}

        risk = self.analyze(symbol)
        if risk.get('error'):
            return risk

        # ATR（用日波動率近似）
        daily_vol = risk['returns']['annual_volatility'] / np.sqrt(self.TRADING_DAYS) / 100
        atr_approx = price * daily_vol * 1.5  # 近似 ATR

        # 方法1：固定風險法（R = max_loss_pct × capital）
        risk_amount = capital * max_loss_pct
        shares_risk = int(risk_amount / (price * stop_loss_pct))

        # 方法2：ATR 法
        shares_atr = int(risk_amount / (atr_approx * 2)) if atr_approx > 0 else 0

        # 方法3：Kelly Criterion
        kelly = risk['position_sizing']['half_kelly']
        shares_kelly = int(capital * kelly / price) if kelly > 0 else 0

        # 取最保守的
        recommended = min(shares_risk, shares_atr) if shares_atr > 0 else shares_risk
        recommended = max(recommended, 0)

        # 台股 1 張 = 1000 股
        lots = recommended // 1000
        position_value = lots * 1000 * price
        position_pct = position_value / capital * 100 if capital > 0 else 0

        return {
            'symbol': symbol,
            'price': price,
            'capital': capital,
            'methods': {
                'fixed_risk': {'shares': shares_risk, 'lots': shares_risk // 1000},
                'atr_based': {'shares': shares_atr, 'lots': shares_atr // 1000, 'atr': round(atr_approx, 2)},
                'kelly': {'shares': shares_kelly, 'lots': shares_kelly // 1000, 'kelly_pct': round(kelly * 100, 2)},
            },
            'recommended': {
                'lots': lots,
                'shares': lots * 1000,
                'value': round(position_value),
                'position_pct': round(position_pct, 1),
                'stop_loss_price': round(price * (1 - stop_loss_pct), 2),
                'max_loss': round(lots * 1000 * price * stop_loss_pct),
            },
            'params': {
                'max_loss_pct': max_loss_pct * 100,
                'stop_loss_pct': stop_loss_pct * 100,
            },
        }

    # ──────────────────────────────────────────────
    #  輔助方法
    # ──────────────────────────────────────────────
    def _get_returns(self, symbol: str, lookback_days: int) -> Optional[List[float]]:
        cutoff = datetime.now() - timedelta(days=int(lookback_days * 1.5))
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'date': 1, 'close': 1}
        ).sort('date', 1))

        if len(prices) < 10:
            return None

        closes = [_to_float(p['close']) for p in prices]
        closes = [c for c in closes if c and c > 0]

        returns = []
        for i in range(1, len(closes)):
            r = (closes[i] - closes[i - 1]) / closes[i - 1]
            # 過濾分割/錯價假跳動（同 _get_returns_dated）：|報酬|>20% 必為未還原分割或爛資料
            if abs(r) <= 0.20:
                returns.append(r)

        return returns[-lookback_days:] if len(returns) > lookback_days else returns

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_price.find_one(
            {'symbol': symbol}, {'close': 1}, sort=[('date', -1)]
        )
        return _to_float(rec['close']) if rec else None

    def _calc_max_drawdown(self, returns: List[float]) -> Tuple[float, int, int]:
        cum = np.cumprod(1 + np.array(returns))
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        max_dd = float(np.min(dd))
        end_idx = int(np.argmin(dd))
        start_idx = int(np.argmax(cum[:end_idx + 1])) if end_idx > 0 else 0
        return max_dd, start_idx, end_idx

    def _get_returns_dated(self, symbol: str, lookback_days: int) -> dict:
        """回傳 {date: 日報酬}（供 beta 按日期對齊；個股與大盤交易日常不同）。"""
        cutoff = datetime.now() - timedelta(days=int(lookback_days * 1.5))
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'date': 1, 'close': 1}
        ).sort('date', 1))
        out: dict = {}
        prev = None
        for p in prices:
            c = _to_float(p['close'])
            if not c or c <= 0:
                continue
            if prev is not None:
                r = (c - prev) / prev
                # 過濾分割/錯價假跳動：台股單日 ±10% 限制，|報酬|>20% 必為未還原分割或爛資料
                if abs(r) <= 0.20:
                    out[p['date']] = r
            prev = c
        return out

    def _calc_beta(self, symbol: str, lookback_days: int) -> float:
        s_d = self._get_returns_dated(symbol, lookback_days)
        # 大盤 proxy 用 TAIEX 發行量加權指數（涵蓋全市場，較 0050 不偏科技股；
        # 由 macro_sync.sync_taiex 維護於 stock_price symbol='TAIEX'）
        m_d = self._get_returns_dated('TAIEX', lookback_days)
        if not s_d or not m_d:
            return 1.0

        # 只用個股與大盤的『共同交易日』對齊，避免切尾錯位導致共變異數失真
        common = sorted(set(s_d) & set(m_d))[-lookback_days:]
        if len(common) < 20:
            return 1.0

        s = np.array([s_d[d] for d in common])
        m = np.array([m_d[d] for d in common])
        cov = np.cov(s, m)
        if cov[1][1] == 0:
            return 1.0
        return round(max(min(float(cov[0][1] / cov[1][1]), 3.0), 0.3), 3)

    def _kelly_criterion(self, returns: np.ndarray) -> float:
        """Kelly Criterion: f* = (p*b - q) / b"""
        wins = returns[returns > 0]
        losses = returns[returns < 0]

        if len(wins) == 0 or len(losses) == 0:
            return 0.0

        p = len(wins) / len(returns)  # 勝率
        q = 1 - p
        b = float(np.mean(wins) / abs(np.mean(losses)))  # 盈虧比

        if b == 0:
            return 0.0

        kelly = (p * b - q) / b
        return max(kelly, 0.0)

    def _risk_grade(self, annual_vol: float, max_dd: float, var_95: float) -> Dict:
        score = 0
        if annual_vol < 0.15:
            score += 3
        elif annual_vol < 0.25:
            score += 2
        elif annual_vol < 0.40:
            score += 1

        if abs(max_dd) < 0.10:
            score += 3
        elif abs(max_dd) < 0.20:
            score += 2
        elif abs(max_dd) < 0.35:
            score += 1

        if var_95 < 0.02:
            score += 3
        elif var_95 < 0.03:
            score += 2
        elif var_95 < 0.05:
            score += 1

        if score >= 7:
            level, desc = '低風險', '波動小、回撤可控'
        elif score >= 4:
            level, desc = '中風險', '波動適中'
        elif score >= 2:
            level, desc = '高風險', '波動大、回撤深'
        else:
            level, desc = '極高風險', '劇烈波動，建議降低部位'

        return {'level': level, 'score': score, 'description': desc}


# ──────────────────────────────────────────────
#  CLI 測試
# ──────────────────────────────────────────────
if __name__ == '__main__':
    ra = RiskAnalyzer()
    test_symbols = ['2330', '2317', '2454', '0056']

    for sym in test_symbols:
        print(f"\n{'='*55}")
        r = ra.analyze(sym)
        if r.get('error'):
            print(f"  {sym}: {r['error']}")
            continue

        print(f"  {sym} 風險分析 ({r['data_points']} 日)")
        print(f"  年化報酬: {r['returns']['annual_return']:+.2f}%  "
              f"年化波動: {r['returns']['annual_volatility']:.2f}%")
        print(f"  VaR(95%): {r['var']['daily_var_95']:.2f}%  "
              f"CVaR(95%): {r['cvar']['daily_cvar_95']:.2f}%")
        print(f"  最大回撤: {r['drawdown']['max_drawdown']:.2f}%")
        print(f"  Sharpe: {r['ratios']['sharpe']:.3f}  "
              f"Sortino: {r['ratios']['sortino']:.3f}  "
              f"Beta: {r['ratios']['beta']:.2f}")
        print(f"  Kelly: {r['position_sizing']['half_kelly']*100:.1f}%  "
              f"風險: {r['risk_level']['level']}")

    # 投組測試
    print(f"\n{'='*55}")
    print("  投資組合風險分析")
    port = ra.portfolio_risk(['2330', '2317', '0056'], [0.5, 0.3, 0.2])
    if not port.get('error'):
        p = port['portfolio']
        print(f"  年化報酬: {p['annual_return']:+.2f}%  波動: {p['annual_volatility']:.2f}%")
        print(f"  Sharpe: {p['sharpe']:.3f}  最大回撤: {p['max_drawdown']:.2f}%")
        print(f"  分散化比率: {port['diversification_ratio']:.3f}")
        print(f"  相關性矩陣:")
        for i, sym in enumerate(port['correlation_matrix']['symbols']):
            row = port['correlation_matrix']['matrix'][i]
            print(f"    {sym}: {row}")

    # 部位建議
    print(f"\n{'='*55}")
    print("  部位管理建議（資金 100 萬）")
    ps = ra.position_size('2330', capital=1_000_000)
    if not ps.get('error'):
        rec = ps['recommended']
        print(f"  2330 @ {ps['price']}")
        print(f"  建議: {rec['lots']} 張 ({rec['position_pct']:.1f}% 部位)")
        print(f"  停損: {rec['stop_loss_price']}  最大虧損: ${rec['max_loss']:,}")
