#!/usr/bin/env python3
"""即時模擬盤 (Paper Trading)。
============================
以 MongoDB 持久化的虛擬交易帳戶：市價/限價下單、以最新收盤價撮合、
維護現金與持倉、計算市值與已/未實現損益，並套用台股實際交易成本。

集合：
- paper_accounts  : 帳戶（現金、初始資金）
- paper_positions : 持倉（每檔股票的張數、均價）
- paper_orders    : 委託單（含未成交限價單）
- paper_trades    : 成交紀錄（含損益）

Usage:
    from src.portfolio.paper_trading import PaperTradingAccount
    acc = PaperTradingAccount('demo', initial_cash=1_000_000)
    acc.buy('2330', lots=2)                 # 市價買 2 張
    acc.sell('2330', lots=1, limit=1100)    # 限價賣
    acc.process_pending()                   # 撮合限價單
    print(acc.summary())
"""
from __future__ import annotations

import logging
from datetime import datetime

from bson.decimal128 import Decimal128
from pymongo import MongoClient

from src.backtesting.tw_costs import FEE, TAX
from src.domain.collections import (
    COLL_PAPER_ACCOUNTS,
    COLL_PAPER_ORDERS,
    COLL_PAPER_POSITIONS,
    COLL_PAPER_TRADES,
    COLL_STOCK_PRICE,
)

logger = logging.getLogger(__name__)

LOT_SIZE = 1000  # 台股 1 張 = 1000 股


def _to_float(v) -> float | None:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class PaperTradingAccount:
    """單一虛擬帳戶。所有狀態持久化於 MongoDB，可跨程序延續。"""

    def __init__(self, account_id: str, initial_cash: float = 1_000_000,
                 fee_discount: float = 1.0,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.account_id = account_id
        self.fee_discount = fee_discount
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._ensure_account(initial_cash)

    # ── 帳戶 ────────────────────────────────────────────────
    def _ensure_account(self, initial_cash: float) -> None:
        acc = self.db[COLL_PAPER_ACCOUNTS].find_one({"account_id": self.account_id})
        if acc is None:
            self.db[COLL_PAPER_ACCOUNTS].insert_one({
                "account_id": self.account_id,
                "initial_cash": initial_cash,
                "cash": initial_cash,
                "fee_discount": self.fee_discount,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            })

    def _acc(self) -> dict:
        return self.db[COLL_PAPER_ACCOUNTS].find_one({"account_id": self.account_id})

    @property
    def cash(self) -> float:
        return float(self._acc()["cash"])

    def _set_cash(self, cash: float) -> None:
        self.db[COLL_PAPER_ACCOUNTS].update_one(
            {"account_id": self.account_id},
            {"$set": {"cash": round(cash, 2), "updated_at": datetime.now()}},
        )

    # ── 行情 ────────────────────────────────────────────────
    def latest_price(self, symbol: str) -> float | None:
        row = self.db[COLL_STOCK_PRICE].find_one(
            {"symbol": symbol}, {"_id": 0, "close": 1, "date": 1}, sort=[("date", -1)]
        )
        return _to_float(row["close"]) if row else None

    # ── 成本 ────────────────────────────────────────────────
    def _buy_cost(self, amount: float) -> float:
        return amount * FEE * self.fee_discount

    def _sell_cost(self, amount: float) -> float:
        return amount * (FEE * self.fee_discount + TAX)

    # ── 下單 ────────────────────────────────────────────────
    def buy(self, symbol: str, lots: int, limit: float | None = None) -> dict:
        return self._place(symbol, "BUY", lots, limit)

    def sell(self, symbol: str, lots: int, limit: float | None = None) -> dict:
        return self._place(symbol, "SELL", lots, limit)

    def _place(self, symbol: str, side: str, lots: int, limit: float | None) -> dict:
        if lots <= 0:
            return {"status": "rejected", "reason": "張數必須為正整數"}
        price = self.latest_price(symbol)
        if price is None:
            return {"status": "rejected", "reason": f"{symbol} 無行情"}

        # 市價單或限價已滿足 → 直接成交；否則掛單等撮合
        fillable = limit is None or (side == "BUY" and price <= limit) or (side == "SELL" and price >= limit)
        order = {
            "account_id": self.account_id,
            "symbol": symbol,
            "side": side,
            "lots": lots,
            "limit": limit,
            "status": "pending",
            "created_at": datetime.now(),
        }
        if not fillable:
            res = self.db[COLL_PAPER_ORDERS].insert_one(order)
            return {"status": "pending", "order_id": str(res.inserted_id), "ref_price": price}

        fill_price = limit if (limit is not None and side == "BUY") else price
        return self._fill(order, fill_price)

    def _fill(self, order: dict, fill_price: float) -> dict:
        symbol, side, lots = order["symbol"], order["side"], order["lots"]
        shares = lots * LOT_SIZE
        amount = fill_price * shares

        if side == "BUY":
            cost = self._buy_cost(amount)
            total = amount + cost
            if total > self.cash:
                return {"status": "rejected", "reason": f"現金不足(需 {total:,.0f}，有 {self.cash:,.0f})"}
            self._set_cash(self.cash - total)
            self._apply_position(symbol, lots, fill_price)
            realized = None
        else:
            pos = self._position(symbol)
            if pos is None or pos["lots"] < lots:
                return {"status": "rejected", "reason": "持倉不足"}
            cost = self._sell_cost(amount)
            proceeds = amount - cost
            realized = round((fill_price - pos["avg_price"]) * shares - cost, 2)
            self._set_cash(self.cash + proceeds)
            self._reduce_position(symbol, lots)

        trade = {
            "account_id": self.account_id,
            "symbol": symbol,
            "side": side,
            "lots": lots,
            "price": round(fill_price, 2),
            "amount": round(amount, 2),
            "cost": round(cost, 2),
            "realized_pnl": realized,
            "filled_at": datetime.now(),
        }
        self.db[COLL_PAPER_TRADES].insert_one(trade)
        return {"status": "filled", **{k: trade[k] for k in ("symbol", "side", "lots", "price", "realized_pnl")}}

    # ── 持倉 ────────────────────────────────────────────────
    def _position(self, symbol: str) -> dict | None:
        return self.db[COLL_PAPER_POSITIONS].find_one(
            {"account_id": self.account_id, "symbol": symbol}
        )

    def _apply_position(self, symbol: str, lots: int, price: float) -> None:
        pos = self._position(symbol)
        if pos is None:
            self.db[COLL_PAPER_POSITIONS].insert_one({
                "account_id": self.account_id, "symbol": symbol,
                "lots": lots, "avg_price": round(price, 2), "updated_at": datetime.now(),
            })
        else:
            old_lots, old_avg = pos["lots"], pos["avg_price"]
            new_lots = old_lots + lots
            new_avg = (old_avg * old_lots + price * lots) / new_lots
            self.db[COLL_PAPER_POSITIONS].update_one(
                {"_id": pos["_id"]},
                {"$set": {"lots": new_lots, "avg_price": round(new_avg, 2), "updated_at": datetime.now()}},
            )

    def _reduce_position(self, symbol: str, lots: int) -> None:
        pos = self._position(symbol)
        if pos is None:
            return
        remaining = pos["lots"] - lots
        if remaining <= 0:
            self.db[COLL_PAPER_POSITIONS].delete_one({"_id": pos["_id"]})
        else:
            self.db[COLL_PAPER_POSITIONS].update_one(
                {"_id": pos["_id"]},
                {"$set": {"lots": remaining, "updated_at": datetime.now()}},
            )

    def positions(self) -> list[dict]:
        return list(self.db[COLL_PAPER_POSITIONS].find(
            {"account_id": self.account_id}, {"_id": 0}
        ))

    # ── 撮合掛單 ────────────────────────────────────────────
    def process_pending(self) -> list[dict]:
        """以最新行情嘗試撮合所有未成交限價單。"""
        pending = list(self.db[COLL_PAPER_ORDERS].find(
            {"account_id": self.account_id, "status": "pending"}
        ))
        filled = []
        for order in pending:
            price = self.latest_price(order["symbol"])
            if price is None:
                continue
            limit, side = order["limit"], order["side"]
            if (side == "BUY" and price <= limit) or (side == "SELL" and price >= limit):
                fill_price = limit if side == "BUY" else price
                res = self._fill(order, fill_price)
                new_status = "filled" if res["status"] == "filled" else "rejected"
                self.db[COLL_PAPER_ORDERS].update_one(
                    {"_id": order["_id"]}, {"$set": {"status": new_status, "closed_at": datetime.now()}}
                )
                if new_status == "filled":
                    filled.append(res)
        return filled

    # ── 結算 ────────────────────────────────────────────────
    def summary(self) -> dict:
        """帳戶總覽：現金、持倉市值、未實現損益、總權益、報酬率。"""
        acc = self._acc()
        cash = float(acc["cash"])
        initial = float(acc["initial_cash"])

        holdings = []
        market_value = 0.0
        unrealized = 0.0
        for pos in self.positions():
            price = self.latest_price(pos["symbol"])
            if price is None:
                continue
            shares = pos["lots"] * LOT_SIZE
            mv = price * shares
            pnl = (price - pos["avg_price"]) * shares
            market_value += mv
            unrealized += pnl
            holdings.append({
                "symbol": pos["symbol"],
                "lots": pos["lots"],
                "avg_price": pos["avg_price"],
                "last_price": round(price, 2),
                "market_value": round(mv),
                "unrealized_pnl": round(pnl),
                "return_pct": round((price / pos["avg_price"] - 1) * 100, 2),
            })

        realized = sum(
            float(t.get("realized_pnl") or 0)
            for t in self.db[COLL_PAPER_TRADES].find(
                {"account_id": self.account_id, "side": "SELL"}, {"realized_pnl": 1}
            )
        )
        equity = cash + market_value
        return {
            "account_id": self.account_id,
            "initial_cash": round(initial),
            "cash": round(cash),
            "market_value": round(market_value),
            "equity": round(equity),
            "unrealized_pnl": round(unrealized),
            "realized_pnl": round(realized),
            "total_return_pct": round((equity / initial - 1) * 100, 2) if initial else 0.0,
            "holdings": holdings,
            "pending_orders": self.db[COLL_PAPER_ORDERS].count_documents(
                {"account_id": self.account_id, "status": "pending"}
            ),
        }

    def reset(self) -> None:
        """清空此帳戶所有持倉/委託/成交並重設現金。"""
        for coll in (COLL_PAPER_POSITIONS, COLL_PAPER_ORDERS, COLL_PAPER_TRADES):
            self.db[coll].delete_many({"account_id": self.account_id})
        self._set_cash(float(self._acc()["initial_cash"]))


def _demo() -> None:
    acc = PaperTradingAccount("demo")
    acc.reset()
    print(acc.buy("2330", lots=2))
    print(acc.process_pending())
    for k, v in acc.summary().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    _demo()
