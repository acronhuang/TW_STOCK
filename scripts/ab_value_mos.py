#!/usr/bin/env python3
"""A/B 回測:value-only 有沒有加 margin_of_safety_pit(維4 驗證)。
同一窗、同引擎(v2.0 純因子),只差 value 因子組成。DCF安全邊際 direction +1(越低估越好)。
"""
import sys
import json

sys.path.append("/home/mdsadmin/Stock/tw-stock-analysis/src")
sys.path.append("/home/mdsadmin/Stock/tw-stock-analysis/scripts")
from pymongo import MongoClient
from backtest_integrated_v21 import BacktestV21

VALUE_BASE = {"weight": 1.0, "factors": {
    "pe_ratio": {"weight": 0.40, "direction": -1},
    "pb_ratio": {"weight": 0.35, "direction": -1},
    "earnings_yield": {"weight": 0.25, "direction": 1}}}

VALUE_MOS = {"weight": 1.0, "factors": {
    "pe_ratio": {"weight": 0.30, "direction": -1},
    "pb_ratio": {"weight": 0.25, "direction": -1},
    "earnings_yield": {"weight": 0.20, "direction": 1},
    "margin_of_safety_pit": {"weight": 0.25, "direction": 1}}}

START, END = "2023-04-01", "2026-06-30"   # margin_of_safety_pit 自 2023-03-31 起有值


def run(value_cfg, label):
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    bt = BacktestV21(db, initial_capital=10_000_000, rebalance_frequency="monthly", quality_source="none")
    for strat in (bt.strategy_v21.factor_strategy, bt.strategy_v20):
        strat.update_config({"momentum": None, "quality": None, "value": value_cfg})
    res = bt.run(START, END, strategy_version="v2.0")
    m = res["metrics"]
    print("RESULT %-16s :: annual=%.2f%% sharpe=%.3f mdd=%.2f%% win=%.1f%% trades=%d" % (
        label, m["annual_return"] * 100, m["sharpe_ratio"], m["max_drawdown"] * 100,
        m["win_rate"] * 100, m["completed_trades"]))
    return m


if __name__ == "__main__":
    print("=== A/B value factor：%s ~ %s ===" % (START, END))
    run(VALUE_BASE, "value(pe/pb/ey)")
    run(VALUE_MOS, "value+DCF安全邊際")
