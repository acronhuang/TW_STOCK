#!/usr/bin/env python3
"""StockRanker quality A/B:加/不加 quality 是否更好(2014-2026 長窗口)。

背景:2026-07-28 把 live StockRanker 的 quality 權重砍到 0(基於白天 v21「quality無溢酬」的外推)。
本 A/B 用延長後的 stock_factors(2013+ 全量重算)正式驗證。

因子全取自 stock_factors(逐日計算=PIT,避開健康分/法人的前視):
  value    = earnings_yield + dividend_yield(pb 資料缺,與 production 現況一致)
  momentum = return_6m
  quality  = roe + operating_margin(StockRanker 的 quality 成分)
月頻換手,產業中性 z-score 合成,top 分位等權,還原價算前瞻報酬(winsor 1/99),扣往返成本 0.585%。

用法: ab_stockranker_quality.py --start 2014-01-01 --end 2026-06-30 --topq 5
"""
import argparse
from datetime import datetime

import numpy as np
import pandas as pd
from bson.decimal128 import Decimal128
from pymongo import MongoClient

import sys
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from scripts.factor_lab import FactorLab   # noqa: E402

ROUND_TRIP = 0.1425 / 100 * 2 + 0.3 / 100   # 0.585%


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else np.nan


def build_panel(lab, dates):
    db = lab.db
    sec = lab.sectors()
    FIELDS = {"earnings_yield": 1, "dividend_yield": 1, "roe": 1,
              "operating_margin": 1, "return_6m": 1, "symbol": 1}
    recs = []
    for k in range(len(dates) - 1):
        d0, d1 = dates[k], dates[k + 1]
        sf = {}
        for r in db.stock_factors.find({"date": d0}, FIELDS):
            s = r.get("symbol")
            if s:
                sf[s] = r
        p0 = lab._adj_close_on(d0)
        p1 = lab._adj_close_on(d1)
        for s in set(sf) & set(p0) & set(p1) & set(sec):
            if p0[s] <= 0:
                continue
            r = sf[s]
            recs.append({
                "date": d0, "symbol": s, "sector": sec[s],
                "ey": _f(r.get("earnings_yield")), "dy": _f(r.get("dividend_yield")),
                "roe": _f(r.get("roe")), "om": _f(r.get("operating_margin")),
                "mom": _f(r.get("return_6m")),
                "fwd": p1[s] / p0[s] - 1,
            })
    return pd.DataFrame(recs)


def sector_z(df, cols):
    def z(g):
        for c in cols:
            m, sd = g[c].mean(), g[c].std()
            g[c + "_z"] = (g[c] - m) / sd if sd and sd > 0 else 0.0
        return g
    return df.groupby(["date", "sector"], group_keys=False).apply(z)


def run(df, weights, topq=5):
    d = df.copy()
    d["score"] = sum(w * d[c].fillna(0) for c, w in weights.items())
    rets, prev = [], None
    for dt, g in d.groupby("date"):
        if len(g) < 30:
            continue
        g = g.copy()
        try:
            g["q"] = pd.qcut(g["score"].rank(method="first"), topq, labels=False) + 1
        except ValueError:
            continue
        top = g[g["q"] == topq]
        cur = set(top["symbol"])
        lo, hi = top["fwd"].quantile([0.01, 0.99])
        gross = top["fwd"].clip(lo, hi).mean()
        turn = 1.0 if prev is None else len(cur - prev) / max(len(cur), 1)
        rets.append((dt, gross - turn * ROUND_TRIP))
        prev = cur
    return pd.Series({dt: r for dt, r in rets}).sort_index()


def metrics(ser, name):
    if ser.empty:
        return f"{name}: 無資料"
    n = len(ser)
    ann = (1 + ser).prod() ** (12 / n) - 1
    sharpe = ser.mean() / ser.std() * np.sqrt(12) if ser.std() else np.nan
    eq = (1 + ser).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    hit = (ser > 0).mean()
    return f"{name:<32} 年化{ann*100:+6.1f}% | Sharpe{sharpe:+.2f} | MDD{mdd*100:6.1f}% | 勝率{hit*100:.0f}% | {n}期"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--topq", type=int, default=5)
    a = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    lab = FactorLab(db)
    dates = lab.month_end_dates(datetime.strptime(a.start, "%Y-%m-%d"),
                                datetime.strptime(a.end, "%Y-%m-%d"))
    print(f"換手日 {len(dates)} 個,建 panel...", flush=True)
    df = build_panel(lab, dates)
    df = sector_z(df, ["ey", "dy", "roe", "om", "mom"])
    print(f"panel {len(df):,} 檔·期,{df['date'].nunique()} 期,{a.start}~{a.end}\n", flush=True)

    # value = ey+dy;momentum = mom;quality = roe+om
    configs = {
        "不加quality(value+mom)":      {"ey_z": 0.30, "dy_z": 0.20, "mom_z": 0.50},
        "加quality(value+mom+qual)":   {"ey_z": 0.25, "dy_z": 0.15, "mom_z": 0.35,
                                        "roe_z": 0.125, "om_z": 0.125},
        "純quality(對照)":             {"roe_z": 0.5, "om_z": 0.5},
    }
    print(f"=== StockRanker quality A/B  Top{a.topq}分位等權 月頻 含成本 ===")
    series = {}
    for name, w in configs.items():
        ser = run(df, w, a.topq)
        series[name] = ser
        print(metrics(ser, name), flush=True)
    bench = lab.bench()
    bret = []
    for k in range(len(dates) - 1):
        b0 = bench[bench.index <= dates[k]]
        b1 = bench[bench.index <= dates[k + 1]]
        if len(b0) and len(b1):
            bret.append((dates[k], b1.iloc[-1] / b0.iloc[-1] - 1))
    bser = pd.Series({d: r for d, r in bret}).sort_index()
    print(metrics(bser, "0050 大盤基準"))


if __name__ == "__main__":
    main()
