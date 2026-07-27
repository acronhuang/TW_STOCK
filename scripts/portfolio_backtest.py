#!/usr/bin/env python3
"""驗證因子組合:value-only vs value+op_margin vs value+op_margin+fcf。

月頻換手,產業中性 z-score 合成分數,選 top 分位等權,用還原價算報酬。
輸出各組合:年化報酬 / Sharpe / 最大回撤 / 勝率,並與大盤(0050)對比。

用法: portfolio_backtest.py --start 2016-01-01 --end 2026-06-30 --topq 5
"""
import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from bson.decimal128 import Decimal128
from pymongo import MongoClient

import sys
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from scripts.factor_lab import FactorLab   # noqa: E402


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else np.nan


def build_panel(lab, dates, fwd=1):
    """每換手日:ey/book_yield(stock_factors) + op_margin/fcf(fundamental PIT) + sector + 前瞻報酬。"""
    db = lab.db
    sec = lab.sectors()
    recs = []
    for k in range(len(dates) - fwd):
        d0, d1 = dates[k], dates[k + fwd]
        # 價值(stock_factors 日頻)
        sf = {}
        for r in db.stock_factors.find({"date": d0}, {"symbol": 1, "earnings_yield": 1, "pb_ratio": 1}):
            sf[r["symbol"]] = (_f(r.get("earnings_yield")), _f(r.get("pb_ratio")))
        # 品質(fundamental PIT:available_from<=d0 最新期)
        pipe = [{"$match": {"available_from": {"$lte": d0}}},
                {"$sort": {"available_from": -1}},
                {"$group": {"_id": "$stock_id", "op": {"$first": "$op_margin"}, "fcf": {"$first": "$fcf_margin"}}}]
        fund = {r["_id"]: (_f(r.get("op")), _f(r.get("fcf"))) for r in db.fundamental_factors.aggregate(pipe)}
        p0 = lab._adj_close_on(d0)
        p1 = lab._adj_close_on(d1)
        reg = lab.regime_of(d0)
        for s in set(sf) & set(fund) & set(p0) & set(p1) & set(sec):
            ey, pb = sf[s]
            op, fcf = fund[s]
            if p0[s] <= 0:
                continue
            recs.append({
                "date": d0, "symbol": s, "sector": sec[s],
                "ey": ey, "by": (1.0 / pb if pb and pb > 0 else np.nan),
                "op": op, "fcf": fcf,
                "fwd": p1[s] / p0[s] - 1, "regime": reg,
            })
    return pd.DataFrame(recs)


def sector_z(df, cols):
    def z(g):
        for c in cols:
            m, s = g[c].mean(), g[c].std()
            g[c + "_z"] = (g[c] - m) / s if s and s > 0 else 0.0
        return g
    return df.groupby(["date", "sector"], group_keys=False).apply(z)


ROUND_TRIP = 0.1425 / 100 * 2 + 0.3 / 100   # 手續費雙邊0.1425% + 賣出證交稅0.3% = 0.585%


def run_config(df, weights, topq=5, cost=True):
    """weights: {factor_z_col: w}。合成分數→每日 top 分位等權→月報酬序列。
    cost=True 扣交易成本:每期 turnover × 往返成本(0.585%);turnover 由前後持股集合算。"""
    d = df.copy()
    d["score"] = sum(w * d[c].fillna(0) for c, w in weights.items())
    d = d.dropna(subset=[c.replace("_z", "") for c in weights])
    rets = []
    prev_set = None
    for dt, g in d.groupby("date"):
        if len(g) < 30:
            continue
        g = g.copy()
        try:
            g["q"] = pd.qcut(g["score"].rank(method="first"), topq, labels=False) + 1
        except ValueError:
            continue
        top = g[g["q"] == topq]
        cur_set = set(top["symbol"])
        lo, hi = top["fwd"].quantile([0.01, 0.99])
        gross = top["fwd"].clip(lo, hi).mean()
        # turnover:相對前一期換掉的比例(單邊);往返成本近似 turnover×ROUND_TRIP
        if prev_set is None:
            turn = 1.0
        else:
            turn = len(cur_set - prev_set) / max(len(cur_set), 1)
        net = gross - (turn * ROUND_TRIP if cost else 0.0)
        rets.append((dt, net, gross, turn))
        prev_set = cur_set
    ser = pd.Series({dt: n for dt, n, _, _ in rets}).sort_index()
    turns = [t for _, _, _, t in rets]
    ser.attrs["avg_turnover"] = float(np.mean(turns)) if turns else 0.0
    return ser


def metrics(ser, name):
    if ser.empty:
        return f"{name}: 無資料"
    n = len(ser)
    ann = (1 + ser).prod() ** (12 / n) - 1        # 月頻→年化
    sharpe = ser.mean() / ser.std() * np.sqrt(12) if ser.std() else np.nan
    eq = (1 + ser).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    hit = (ser > 0).mean()
    turn = ser.attrs.get("avg_turnover", 0.0)
    return (f"{name:<28} 年化{ann*100:+6.1f}% | Sharpe{sharpe:+.2f} | MDD{mdd*100:6.1f}% | "
            f"月勝率{hit*100:.0f}% | 週轉{turn*100:.0f}% | {n}期")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--topq", type=int, default=5)
    a = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    lab = FactorLab(db)
    dates = lab.month_end_dates(datetime.strptime(a.start, "%Y-%m-%d"),
                                datetime.strptime(a.end, "%Y-%m-%d"))
    print(f"換手日 {len(dates)} 個,建 panel...")
    df = build_panel(lab, dates)
    df = sector_z(df, ["ey", "by", "op", "fcf"])
    print(f"panel {len(df):,} 檔·期,{df['date'].nunique()} 期\n")

    configs = {
        "A 純價值(ey+1/pb)":            {"ey_z": 0.5, "by_z": 0.5},
        "B 價值+op_margin":              {"ey_z": 0.35, "by_z": 0.35, "op_z": 0.30},
        "C 價值+op_margin+fcf":          {"ey_z": 0.3, "by_z": 0.3, "op_z": 0.25, "fcf_z": 0.15},
        "D 純op_margin(對照)":          {"op_z": 1.0},
    }
    print(f"=== Top {a.topq} 分位等權,月頻換手,{a.start}~{a.end} ===")
    series = {}
    for name, w in configs.items():
        ser = run_config(df, w, a.topq)
        series[name] = ser
        print(metrics(ser, name))
    # 大盤基準
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
