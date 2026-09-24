#!/usr/bin/env python3
"""Phase A — 最小測試種子資料（僅供 CI / 空測試庫）。

灌入 price-logic 整合測試所需的最小資料集：
  - stock_price：2330 / TAIEX / 0050（各 120 個交易日，2330 與 TAIEX/0050 相關 → beta≈1）
  - stock_factors：2330 最新一筆（return_1m / rsi_14 / pe_ratio …）

涵蓋（needs_data）：test_risk_manager、test_trading_rules（4 類）、
test_trading_rules_steps、test_bdd_macro。

⚠️ 安全護欄：若 stock_price 已有 > 50 個不同 symbol（疑似正式庫），直接拒絕，
   避免誤刪/污染真實資料。CI 空庫（0 symbol）才會執行。

用法：
    MONGODB_URI=mongodb://localhost:27017 MONGODB_DATABASE=tw_stock_analysis \\
        python scripts/seed_test_data.py
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

from pymongo import MongoClient

SEED_SYMBOLS = ("2330", "TAIEX", "0050", "2317", "0056", "2603")
BASES = {"2330": 900.0, "TAIEX": 23000.0, "0050": 190.0, "2317": 210.0, "0056": 38.0, "2603": 210.0}
N_DAYS = 120
PROD_GUARD_MAX_SYMBOLS = 50


def _business_days(n: int) -> list[datetime]:
    """回傳最近 n 個工作日（升冪，含今天往回），跳過週末。"""
    days: list[datetime] = []
    d = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    while len(days) < n:
        if d.weekday() < 5:  # 0-4 = 週一到週五
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def _gen_series(rng: random.Random) -> dict[str, list[float]]:
    """產生相關報酬序列：2330 / 0050 ≈ beta 1 對 TAIEX（含個股雜訊）。"""
    dates = _business_days(N_DAYS)
    market_ret = [rng.gauss(0.0003, 0.010) for _ in dates]
    series: dict[str, list[float]] = {}
    for sym in SEED_SYMBOLS:
        price = BASES[sym]
        closes = []
        for i in range(len(dates)):
            if sym == "TAIEX":
                r = market_ret[i]
            else:  # 個股 = 大盤*1.0 + 雜訊 → beta≈1（落在 0.3–3.0）
                r = market_ret[i] + rng.gauss(0.0, 0.008)
            r = max(-0.19, min(0.19, r))  # |日報酬| < 20%（避開分割過濾）
            price = max(1.0, price * (1 + r))
            closes.append(round(price, 2))
        series[sym] = closes
    series["_dates"] = dates  # type: ignore[assignment]
    return series


def seed(db) -> None:
    existing = db["stock_price"].distinct("symbol")
    if len(existing) > PROD_GUARD_MAX_SYMBOLS:
        raise SystemExit(
            f"拒絕執行：stock_price 已有 {len(existing)} 個 symbol（疑似正式庫）。"
            "本腳本僅供空測試庫。"
        )

    rng = random.Random(20260924)
    series = _gen_series(rng)
    dates: list[datetime] = series.pop("_dates")  # type: ignore[assignment]

    # stock_price
    db["stock_price"].delete_many({"symbol": {"$in": list(SEED_SYMBOLS)}})
    docs = []
    for sym in SEED_SYMBOLS:
        closes = series[sym]
        for d, close in zip(dates, closes):
            high = round(close * (1 + rng.uniform(0, 0.015)), 2)
            low = round(close * (1 - rng.uniform(0, 0.015)), 2)
            open_ = round(close * (1 + rng.uniform(-0.01, 0.01)), 2)
            docs.append({
                "symbol": sym,
                "date": d,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": rng.randint(10_000, 50_000) * 1000,
            })
    db["stock_price"].insert_many(docs)

    # stock_factors（2330 最新一筆；buy_three_questions 讀 return_1m / rsi_14）
    db["stock_factors"].delete_many({"symbol": "2330"})
    c = series["2330"]
    ret_1m = (c[-1] - c[-21]) / c[-21] * 100 if len(c) > 21 else 0.0
    db["stock_factors"].insert_one({
        "symbol": "2330",
        "date": dates[-1],
        "pe_ratio": 18.5,
        "pb_ratio": 4.2,
        "dividend_yield": 2.1,
        "return_1m": round(ret_1m, 2),
        "rsi_14": 55.0,
    })

    print(
        f"✅ 已灌入種子：stock_price {len(docs)} 筆（{', '.join(SEED_SYMBOLS)}）"
        f"、stock_factors 2330 x1（{len(dates)} 個交易日 {dates[0]:%Y-%m-%d}→{dates[-1]:%Y-%m-%d}）"
    )


def main() -> None:
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DATABASE", "tw_stock_analysis")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        seed(client[db_name])
    finally:
        client.close()


if __name__ == "__main__":
    main()
