#!/usr/bin/env python3
"""選擇權定價與風控模組：Black-Scholes + Greeks + 隱含波動率 + 垂直價差策略。
=========================================================================
純數學模組（不依賴 MongoDB），供台指選擇權(TXO)/個股選擇權的部位風控使用。

慣例：
- 到期時間 T 以「年」為單位（距到期天數 / 365）。
- 利率 r、波動率 sigma 以年化小數表示（r=0.015 代表 1.5%）。
- 台指選擇權每點 50 元 → 用 contract_multiplier 參數換算金額。

Usage:
    from src.analysis.options_pricing import OptionsPricer, VerticalSpread
    p = OptionsPricer.price(S=18000, K=18200, T=30/365, r=0.015, sigma=0.18, kind='call')
    g = OptionsPricer.greeks(S=18000, K=18200, T=30/365, r=0.015, sigma=0.18, kind='call')
    iv = OptionsPricer.implied_vol(market_price=120, S=18000, K=18200, T=30/365, r=0.015, kind='call')
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm

RISK_FREE_RATE = 0.015  # 台灣十年期公債近似
DAYS_PER_YEAR = 365.0


class OptionsPricer:
    """Black-Scholes 歐式選擇權定價與 Greeks。"""

    @staticmethod
    def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            raise ValueError("S/K/T/sigma 必須為正數")
        d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    @staticmethod
    def price(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> float:
        """理論價（每點/每股）。kind: 'call' | 'put'。"""
        d1, d2 = OptionsPricer._d1_d2(S, K, T, r, sigma)
        if kind == "call":
            return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        if kind == "put":
            return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        raise ValueError("kind 必須為 'call' 或 'put'")

    @staticmethod
    def greeks(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> dict:
        """完整 Greeks。theta 為每日衰減、vega/rho 為每 1% 變動的敏感度。"""
        d1, d2 = OptionsPricer._d1_d2(S, K, T, r, sigma)
        pdf_d1 = norm.pdf(d1)
        sqrt_t = math.sqrt(T)
        disc = math.exp(-r * T)

        gamma = pdf_d1 / (S * sigma * sqrt_t)
        vega = S * pdf_d1 * sqrt_t / 100.0  # 每 +1% 波動率

        if kind == "call":
            delta = norm.cdf(d1)
            theta = (-S * pdf_d1 * sigma / (2 * sqrt_t) - r * K * disc * norm.cdf(d2)) / DAYS_PER_YEAR
            rho = K * T * disc * norm.cdf(d2) / 100.0
        elif kind == "put":
            delta = norm.cdf(d1) - 1.0
            theta = (-S * pdf_d1 * sigma / (2 * sqrt_t) + r * K * disc * norm.cdf(-d2)) / DAYS_PER_YEAR
            rho = -K * T * disc * norm.cdf(-d2) / 100.0
        else:
            raise ValueError("kind 必須為 'call' 或 'put'")

        return {
            "price": float(round(OptionsPricer.price(S, K, T, r, sigma, kind), 4)),
            "delta": float(round(delta, 4)),
            "gamma": float(round(gamma, 6)),
            "theta": float(round(theta, 4)),     # 每日
            "vega": float(round(vega, 4)),       # 每 +1% IV
            "rho": float(round(rho, 4)),         # 每 +1% 利率
        }

    @staticmethod
    def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                    kind: str = "call", tol: float = 1e-5, max_iter: int = 100) -> float | None:
        """以 Brent 區間法反解隱含波動率；無解回 None。"""
        intrinsic = max(0.0, (S - K) if kind == "call" else (K - S)) * math.exp(-r * 0)
        if market_price < intrinsic - tol:
            return None

        lo, hi = 1e-4, 5.0
        try:
            p_lo = OptionsPricer.price(S, K, T, r, lo, kind) - market_price
            p_hi = OptionsPricer.price(S, K, T, r, hi, kind) - market_price
        except ValueError:
            return None
        if p_lo * p_hi > 0:
            return None

        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            p_mid = OptionsPricer.price(S, K, T, r, mid, kind) - market_price
            if abs(p_mid) < tol:
                return round(mid, 6)
            if p_lo * p_mid < 0:
                hi = mid
            else:
                lo, p_lo = mid, p_mid
        return round(0.5 * (lo + hi), 6)


@dataclass
class SpreadLeg:
    kind: str       # 'call' | 'put'
    K: float
    side: str       # 'long' | 'short'
    premium: float  # 權利金（點）


class VerticalSpread:
    """垂直價差策略分析（牛/熊 × call/put）。

    四種標準組合：
    - bull_call : 買低履約 call + 賣高履約 call（看多，有限風險/報酬）
    - bear_call : 賣低履約 call + 買高履約 call（看空，收權利金）
    - bull_put  : 賣高履約 put + 買低履約 put（看多，收權利金）
    - bear_put  : 買高履約 put + 賣低履約 put（看空，有限風險/報酬）
    """

    STRATEGIES = ("bull_call", "bear_call", "bull_put", "bear_put")

    def __init__(self, strategy: str, K_low: float, K_high: float,
                 S: float, T: float, r: float = RISK_FREE_RATE,
                 sigma: float = 0.18, contract_multiplier: float = 50.0):
        if strategy not in self.STRATEGIES:
            raise ValueError(f"strategy 必須為 {self.STRATEGIES}")
        if K_low >= K_high:
            raise ValueError("K_low 必須小於 K_high")
        self.strategy = strategy
        self.K_low = K_low
        self.K_high = K_high
        self.S = S
        self.T = T
        self.r = r
        self.sigma = sigma
        self.mult = contract_multiplier
        self.legs = self._build_legs()

    def _premium(self, K: float, kind: str) -> float:
        return OptionsPricer.price(self.S, K, self.T, self.r, self.sigma, kind)

    def _build_legs(self) -> list[SpreadLeg]:
        lo, hi = self.K_low, self.K_high
        if self.strategy == "bull_call":
            return [SpreadLeg("call", lo, "long", self._premium(lo, "call")),
                    SpreadLeg("call", hi, "short", self._premium(hi, "call"))]
        if self.strategy == "bear_call":
            return [SpreadLeg("call", lo, "short", self._premium(lo, "call")),
                    SpreadLeg("call", hi, "long", self._premium(hi, "call"))]
        if self.strategy == "bull_put":
            return [SpreadLeg("put", hi, "short", self._premium(hi, "put")),
                    SpreadLeg("put", lo, "long", self._premium(lo, "put"))]
        # bear_put
        return [SpreadLeg("put", hi, "long", self._premium(hi, "put")),
                SpreadLeg("put", lo, "short", self._premium(lo, "put"))]

    def _net_premium(self) -> float:
        """正值=淨支出(debit)，負值=淨收入(credit)。"""
        net = 0.0
        for leg in self.legs:
            net += leg.premium if leg.side == "long" else -leg.premium
        return net

    def _payoff_at(self, price: float) -> float:
        """到期時每點損益（含權利金）。"""
        total = -self._net_premium()
        for leg in self.legs:
            if leg.kind == "call":
                intrinsic = max(0.0, price - leg.K)
            else:
                intrinsic = max(0.0, leg.K - price)
            total += intrinsic if leg.side == "long" else -intrinsic
        return total

    def analyze(self) -> dict:
        """回傳最大獲利/最大虧損/損益兩平/淨 Greeks/風報比。"""
        width = self.K_high - self.K_low
        net = self._net_premium()  # +debit / -credit

        payoff_low = self._payoff_at(self.K_low)
        payoff_high = self._payoff_at(self.K_high)
        max_profit = max(payoff_low, payoff_high)
        max_loss = min(payoff_low, payoff_high)

        # 損益兩平點（兩履約間線性內插過零點）
        breakeven = None
        if (payoff_low < 0 < payoff_high) or (payoff_high < 0 < payoff_low):
            frac = abs(payoff_low) / (abs(payoff_low) + abs(payoff_high))
            breakeven = float(round(self.K_low + frac * width, 2))

        net_greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        for leg in self.legs:
            g = OptionsPricer.greeks(self.S, leg.K, self.T, self.r, self.sigma, leg.kind)
            sign = 1 if leg.side == "long" else -1
            for k in net_greeks:
                net_greeks[k] += sign * g[k]
        net_greeks = {k: float(round(v, 4)) for k, v in net_greeks.items()}

        rr = float(round(abs(max_profit / max_loss), 2)) if max_loss != 0 else None

        return {
            "strategy": self.strategy,
            "legs": [{"kind": l.kind, "K": l.K, "side": l.side, "premium": float(round(l.premium, 2))}
                     for l in self.legs],
            "net_premium_pts": float(round(net, 2)),
            "net_cost_twd": float(round(net * self.mult)),  # +支出 / -收入
            "max_profit_pts": float(round(max_profit, 2)),
            "max_loss_pts": float(round(max_loss, 2)),
            "max_profit_twd": float(round(max_profit * self.mult)),
            "max_loss_twd": float(round(max_loss * self.mult)),
            "breakeven": breakeven,
            "risk_reward": rr,
            "net_greeks": net_greeks,
        }


def _demo() -> None:
    S, T, r, sigma = 18000, 30 / 365, RISK_FREE_RATE, 0.18
    print("=== Greeks (call 18200) ===")
    print(OptionsPricer.greeks(S, 18200, T, r, sigma, "call"))
    print("\n=== Bull Call Spread 17800/18200 ===")
    sp = VerticalSpread("bull_call", 17800, 18200, S, T, r, sigma)
    for k, v in sp.analyze().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _demo()
