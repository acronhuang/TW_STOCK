#!/usr/bin/env python3
"""Phase A — 最小測試種子資料（僅供 CI / 空測試庫）。

灌入 price-logic 整合測試所需的最小資料集:
  - stock_price:10 檔非-ETF 個股 + TAIEX + 0050(beta 基準) + 0056(ETF),各 120 個交易日
  - stock_factors:各檔最新一筆(return_1m / rsi_14 / pe_ratio …)+ 2330 PE 歷史

涵蓋(needs_data):test_risk_manager、test_trading_rules(4 類)、
test_trading_rules_steps、test_bdd_macro、test_valuation(6)、test_ranking_steps(2)。

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
from bson.decimal128 import Decimal128


def _dec(x: float) -> Decimal128:
    return Decimal128(f"{x:.4f}")

# 10 檔非-ETF 4 位數個股(供 StockRanker.rank需 exclude_etf 後≥檔)
#   + 大盤 TAIEX / 基準 0050(beta) / ETF 0056(DDM 測試)。
SEED_SYMBOLS = (
    "2330", "2317", "2454", "2603", "2412",
    "2308", "2881", "2882", "1301", "3008",
    "TAIEX", "0050", "0056",
)
BASES = {
    "2330": 900.0, "2317": 210.0, "2454": 1200.0, "2603": 210.0, "2412": 125.0,
    "2308": 480.0, "2881": 90.0, "2882": 42.0, "1301": 95.0, "3008": 2500.0,
    "TAIEX": 23000.0, "0050": 190.0, "0056": 38.0,
}
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
                "open": _dec(open_),
                "high": _dec(high),
                "low": _dec(low),
                "close": _dec(close),  # 正式 schema 用 Decimal128（消費端 .to_decimal()）
                "volume": rng.randint(10_000, 50_000) * 1000,
            })
    db["stock_price"].insert_many(docs)

    # stock_factors（每支一筆最新；必須含 StockRanker.FIELDS 全部欄位，否則建構時 ValueError）
    db["stock_factors"].delete_many({"symbol": {"$in": list(SEED_SYMBOLS)}})
    fdocs = []
    for sym in SEED_SYMBOLS:
        if sym == "TAIEX":
            continue
        c = series[sym]
        ret_1m = (c[-1] - c[-21]) / c[-21] * 100 if len(c) > 21 else 0.0
        fdocs.append({
            "symbol": sym,
            "date": dates[-1],
            "pe_ratio": round(rng.uniform(12, 25), 2),
            "pb_ratio": round(rng.uniform(1.5, 5.0), 2),
            "dividend_yield": round(rng.uniform(1.0, 4.0), 2),
            "roe": round(rng.uniform(8.0, 25.0), 2),
            "operating_margin": round(rng.uniform(10.0, 40.0), 2),
            "rsi_14": round(rng.uniform(40.0, 60.0), 1),
            "return_1m": round(ret_1m, 2),
            "volatility_30d": round(rng.uniform(0.18, 0.40), 3),
        })
    db["stock_factors"].insert_many(fdocs)

    # quarterly_earnings（2330：8 季正淨利/營收/EPS → DCF fair_value>0、_get_trailing_eps 可算）
    # → 支援 test_valuation_steps（守衛式斷言，wacc>=8 由 MIN_WACC 保證）。
    now_year = dates[-1].year
    db["quarterly_earnings"].delete_many({"symbol": "2330"})
    qdocs = []
    for yr in (now_year - 2, now_year - 1):  # 2 完整年，每年 4 季（滿足 quarters>=3 與 CAGR min_years=2）
        for season in (1, 2, 3, 4):
            qdocs.append({
                "symbol": "2330",
                "year": yr,
                "season": season,
                "income": {
                    "eps": 10.0,  # 單季 EPS（Q4 < Q1+Q2+Q3 → 直接加總）
                    "net_income": 250_000_000_000,
                    "revenue": 600_000_000_000,
                },
            })
    db["quarterly_earnings"].insert_many(qdocs)

    # taiwan_stock_info（2330 流通在外股數,千股)→ DCF _get_shares_outstanding
    db["taiwan_stock_info"].delete_many({"stock_id": "2330"})
    db["taiwan_stock_info"].insert_one({"stock_id": "2330", "outstanding_shares": 25_930_000})

    # dividend_detail（2330 / 0056:4 個完整年,正現金股利)→ DDM fair_value>0
    # → 支援 test_valuation::TestDDM(test_ddm_returns_fair_value / test_ddm_etf)。
    #   守衛式斷言:資料不足時模型回 reason dict,種子後才真走 fair_value 分支。
    DIV_CASH = {"2330": (10.0, 10.5, 11.0, 11.5), "0056": (1.5, 1.6, 1.75, 1.9)}
    ddocs = []
    for sym, cashes in DIV_CASH.items():
        db["dividend_detail"].delete_many({"stock_id": sym})
        for offset, cash in enumerate(reversed(cashes)):  # 最近年在前
            yr = now_year - 1 - offset
            ddocs.append({
                "stock_id": sym,
                "date": f"{yr}-06-15",
                "cash_earnings_distribution": cash,
                "stock_earnings_distribution": 0.0,
            })
    db["dividend_detail"].insert_many(ddocs)

    # stock_factors PE 歷史（2330:近 36 個月 pe_ratio ∈ (11,23)）→ PE Band 需 ≥20 筆
    # → 支援 test_valuation::TestPEBand::test_pe_band_analysis(否則回『PE 歷史資料不足』)。
    #   皆早於 dates[-1],故 StockRanker 取用的『最新完整 factor』不受影響。
    pe_hist = []
    for m in range(1, 37):
        pe_hist.append({
            "symbol": "2330",
            "date": dates[-1] - timedelta(days=30 * m),
            "pe_ratio": round(rng.uniform(11.0, 23.0), 2),
        })
    db["stock_factors"].insert_many(pe_hist)

    # macro_indicators + institutional_flow → MacroAnalyzer.overview()/market_signal() 可算
    # → 支援 test_bdd_macro、test_cli::test_macro_command(均守衛式/不變式斷言:
    #   score∈[-100,100]、verdict 含 偏多/偏空/中性、returncode 0)。
    # doc schema:{indicator, date, data:{...}, updated_at}(updated_at=now → _is_fresh 命中。
    db["macro_indicators"].delete_many({"indicator": {"$in": [
        "money_supply", "interest_rate", "cpi", "exchange_rate"]}})
    today_str = f"{dates[-1]:%Y-%m-%d}"
    macro_docs = [
        {"indicator": "money_supply", "data": {"m1b_yoy": 6.5, "m2_yoy": 5.0}},   # M1B>M2 → bullish
        {"indicator": "interest_rate", "data": {"discount_rate": 1.875}},           # <2% → bullish
        {"indicator": "cpi", "data": {"yoy": 2.2}},                                 # 1~3% → 溫和 bullish
        {"indicator": "exchange_rate", "data": {"usd_twd": 31.5, "change_1m": -0.3}},  # |0.3|<0.5 → 無訊號
    ]
    for d in macro_docs:
        d["date"] = today_str
        d["updated_at"] = datetime.now()
    db["macro_indicators"].insert_many(macro_docs)

    # institutional_flow(近 5 日外資買超 → _get_taiex_summary foreign_net_5d>0 → bullish)
    db["institutional_flow"].delete_many({"symbol": "2330"})
    inst_docs = [{
        "symbol": "2330", "date": d,
        "foreign_net": 1_500_000_000, "trust_net": 200_000_000, "total_net": 1_700_000_000,
    } for d in dates[-5:]]
    db["institutional_flow"].insert_many(inst_docs)

    print(
        f"✅ 已灌入種子:stock_price {len(docs)} 筆({', '.join(SEED_SYMBOLS)})"
        f"、stock_factors {len(fdocs)}+{len(pe_hist)} 筆(含 2330 PE 歷史)"
        f"、quarterly_earnings 2330 x{len(qdocs)}、taiwan_stock_info 2330 x1"
        f"、dividend_detail x{len(ddocs)}(2330/0056)"
        f"、macro_indicators x{len(macro_docs)}、institutional_flow 2330 x{len(inst_docs)}"
        f"({len(dates)} 個交易日 {dates[0]:%Y-%m-%d}→{dates[-1]:%Y-%m-%d})"
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
