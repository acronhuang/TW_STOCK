#!/usr/bin/env python3
"""配對交易策略 (Statistical Arbitrage / Pairs Trading)。
====================================================
以共整合(Engle-Granger)尋找長期均衡的股票對，利用價差(spread)均值回歸交易。

因環境僅含 scipy（無 statsmodels），ADF 檢定以 Dickey-Fuller 迴歸自行實作，
臨界值採 MacKinnon(1996) 近似值；p 值僅供排序與門檻判斷。

Usage:
    from src.strategy.pairs_trading import PairsTrader
    pt = PairsTrader()
    res = pt.analyze_pair('2330', '2317')          # 單一對分析
    pairs = pt.find_pairs(['2330','2317','2454','2412'])  # 掃描候選對
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import combinations

import numpy as np
from bson.decimal128 import Decimal128
from pymongo import MongoClient

from src.domain.collections import COLL_STOCK_PRICE

logger = logging.getLogger(__name__)

# Engle-Granger 無截距殘差 ADF 臨界值（MacKinnon 近似，單一自變數）
_EG_CRIT = {0.01: -3.90, 0.05: -3.34, 0.10: -3.04}


def _to_float(v) -> float | None:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ols(y: np.ndarray, x: np.ndarray) -> tuple[float, float, np.ndarray]:
    """y = alpha + beta*x，回 (alpha, beta, residuals)。"""
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])
    resid = y - (alpha + beta * x)
    return alpha, beta, resid


def _adf_tstat(series: np.ndarray) -> float:
    """Dickey-Fuller 檢定統計量：Δs_t = rho*s_{t-1} + e_t 的 rho t 值。"""
    s = np.asarray(series, dtype=float)
    ds = np.diff(s)
    lag = s[:-1]
    if len(ds) < 10 or np.std(lag) == 0:
        return 0.0
    X = lag.reshape(-1, 1)
    coef, *_ = np.linalg.lstsq(X, ds, rcond=None)
    rho = float(coef[0])
    resid = ds - rho * lag
    dof = len(ds) - 1
    se = float(np.sqrt(np.sum(resid ** 2) / dof / np.sum(lag ** 2))) if dof > 0 else 0.0
    return rho / se if se > 0 else 0.0


def _adf_pvalue(tstat: float) -> float:
    """以臨界值粗略換算 p 值（越負越顯著）。"""
    if tstat <= _EG_CRIT[0.01]:
        return 0.01
    if tstat <= _EG_CRIT[0.05]:
        return 0.05
    if tstat <= _EG_CRIT[0.10]:
        return 0.10
    return 0.50


def _half_life(spread: np.ndarray) -> float | None:
    """OU 過程均值回歸半衰期（天）；無回歸特性回 None。"""
    s = np.asarray(spread, dtype=float)
    lag = s[:-1]
    ds = np.diff(s)
    _, beta, _ = _ols(ds, lag)
    if beta >= 0:
        return None
    return round(-np.log(2) / beta, 1)


class PairsTrader:
    """配對交易：共整合檢定 + 價差 z-score 訊號 + 簡易回測。"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    def _load_close(self, symbol: str, lookback_days: int) -> dict[datetime, float]:
        cutoff = datetime.now() - timedelta(days=lookback_days)
        rows = self.db[COLL_STOCK_PRICE].find(
            {"symbol": symbol, "date": {"$gte": cutoff}},
            {"_id": 0, "date": 1, "adj_close": 1, "close": 1},
        ).sort("date", 1)
        out: dict[datetime, float] = {}
        for r in rows:
            px = _to_float(r.get("adj_close")) or _to_float(r.get("close"))
            if px and px > 0:
                out[r["date"]] = px
        return out

    def _aligned(self, s1: str, s2: str, lookback_days: int) -> tuple[np.ndarray, np.ndarray] | None:
        a, b = self._load_close(s1, lookback_days), self._load_close(s2, lookback_days)
        common = sorted(set(a) & set(b))
        if len(common) < 60:
            return None
        return (np.array([a[d] for d in common]), np.array([b[d] for d in common]))

    def analyze_pair(self, s1: str, s2: str, lookback_days: int = 365,
                     entry_z: float = 2.0, exit_z: float = 0.5) -> dict:
        """單一股票對的共整合與當前訊號。"""
        data = self._aligned(s1, s2, lookback_days)
        if data is None:
            return {"pair": [s1, s2], "error": "共同交易日不足(<60)"}
        y, x = data

        # 對數價較穩定
        ly, lx = np.log(y), np.log(x)
        alpha, beta, resid = _ols(ly, lx)
        if beta <= 0:
            return {"pair": [s1, s2], "error": "避險比為負，非有效配對"}

        tstat = _adf_tstat(resid)
        pval = _adf_pvalue(tstat)
        hl = _half_life(resid)

        mu, sd = float(np.mean(resid)), float(np.std(resid))
        z = (resid[-1] - mu) / sd if sd > 0 else 0.0

        if z >= entry_z:
            signal = f"賣 {s1} / 買 {s2}（價差偏高，放空價差）"
        elif z <= -entry_z:
            signal = f"買 {s1} / 賣 {s2}（價差偏低，做多價差）"
        elif abs(z) <= exit_z:
            signal = "平倉/觀望（價差回歸均衡）"
        else:
            signal = "持有/等待"

        cointegrated = bool(pval <= 0.05 and hl is not None and 1 <= hl <= 60)
        corr = float(np.corrcoef(ly, lx)[0, 1])

        return {
            "pair": [s1, s2],
            "cointegrated": cointegrated,
            "hedge_ratio": round(beta, 4),
            "adf_tstat": round(tstat, 4),
            "adf_pvalue": pval,
            "half_life_days": hl,
            "correlation": round(corr, 3),
            "zscore": round(z, 2),
            "spread_mean": round(mu, 4),
            "spread_std": round(sd, 4),
            "signal": signal,
            "n_days": len(y),
        }

    def find_pairs(self, symbols: list[str], lookback_days: int = 365,
                   min_corr: float = 0.7, max_pvalue: float = 0.05) -> list[dict]:
        """在候選池中枚舉所有股票對，回傳共整合且相關性達標者（依 p 值升冪）。"""
        results: list[dict] = []
        for s1, s2 in combinations(sorted(set(symbols)), 2):
            res = self.analyze_pair(s1, s2, lookback_days)
            if res.get("error"):
                continue
            if res["correlation"] >= min_corr and res["adf_pvalue"] <= max_pvalue and res["cointegrated"]:
                results.append(res)
        results.sort(key=lambda r: (r["adf_pvalue"], -r["correlation"]))
        return results

    def backtest_pair(self, s1: str, s2: str, lookback_days: int = 365,
                      entry_z: float = 2.0, exit_z: float = 0.5) -> dict:
        """價差均值回歸回測（市場中性，不含交易成本的毛報酬示意）。"""
        data = self._aligned(s1, s2, lookback_days)
        if data is None:
            return {"pair": [s1, s2], "error": "資料不足"}
        y, x = data
        ly, lx = np.log(y), np.log(x)
        _, beta, resid = _ols(ly, lx)
        mu, sd = float(np.mean(resid)), float(np.std(resid))
        if sd == 0:
            return {"pair": [s1, s2], "error": "價差無波動"}
        z = (resid - mu) / sd

        position = 0  # +1 做多價差, -1 放空價差
        pnl = 0.0
        trades = 0
        wins = 0
        entry_spread = 0.0
        for i in range(1, len(z)):
            if position == 0:
                if z[i] >= entry_z:
                    position, entry_spread = -1, resid[i]
                elif z[i] <= -entry_z:
                    position, entry_spread = 1, resid[i]
            elif abs(z[i]) <= exit_z:
                trade_pnl = position * (resid[i] - entry_spread)
                pnl += trade_pnl
                trades += 1
                wins += 1 if trade_pnl > 0 else 0
                position = 0

        return {
            "pair": [s1, s2],
            "hedge_ratio": round(beta, 4),
            "trades": trades,
            "win_rate": round(wins / trades * 100, 1) if trades else 0.0,
            "total_spread_pnl": round(pnl, 4),
            "entry_z": entry_z,
            "exit_z": exit_z,
            "n_days": len(y),
        }


def _demo() -> None:
    pt = PairsTrader()
    for a, b in [("2330", "2317"), ("2412", "3045")]:
        print(f"=== {a} / {b} ===")
        for k, v in pt.analyze_pair(a, b).items():
            print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    _demo()
