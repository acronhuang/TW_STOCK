#!/usr/bin/env python3
"""2560戰法回測(事件研究)。

對每檔股票逐日:若當日 classify_2560 為『踩25線起動』setup,記錄進場(還原價),
算 +5/+10/+20 日的前瞻報酬。分四情境(縮量/做量/衝量/誘惑)統計勝率/均報酬/中位,
對照「同期任意日買進」的大盤基準,判斷各情境是否真有超額。

- 還原價(adj_close)算報酬 → 除權息不算跌。
- 冷卻期(預設10交易日)避免同一波踩線重複計數。
- 訊號只用當日(含)以前的資料,無未來函數。

用法: backtest_2560.py [--start 2024-01-01] [--cooldown 10]
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient

from src.analysis.strategy_2560 import classify_2560

HORIZONS = [5, 10, 20]


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--cooldown", type=int, default=10)
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    args = ap.parse_args()
    db = MongoClient(args.uri)["tw_stock_analysis"]
    start = datetime.strptime(args.start, "%Y-%m-%d")
    warm = start - timedelta(days=220)

    ser = defaultdict(list)
    cur = None
    for r in db.stock_price.find(
            {"date": {"$gte": warm, "$type": "date"}},
            {"stock_id": 1, "date": 1, "close": 1, "adj_close": 1, "volume": 1}).sort([("stock_id", 1), ("date", 1)]):
        s = r["stock_id"]
        if not (len(s) == 4 and s.isdigit() and not s.startswith("00")):
            continue
        c = _g(r.get("adj_close")) or _g(r.get("close"))
        v = _g(r.get("volume"))
        if c and v is not None:
            ser[s].append((r["date"], c, v))

    res = {sc: {h: [] for h in HORIZONS} for sc in ("縮量", "做量", "衝量", "誘惑")}
    base = {h: [] for h in HORIZONS}
    n_stocks = n_sig = 0
    maxh = max(HORIZONS)
    for s, bars in ser.items():
        if len(bars) < 65 + maxh:
            continue
        n_stocks += 1
        dates = [b[0] for b in bars]
        closes = [b[1] for b in bars]
        vols = [b[2] for b in bars]
        last = -999
        for t in range(64, len(closes) - maxh):
            if dates[t] < start:
                continue
            # 基準:每5個交易日取一個「任意進場」樣本
            if t % 5 == 0:
                for h in HORIZONS:
                    base[h].append((closes[t + h] / closes[t] - 1) * 100)
            r = classify_2560(closes[t - 64:t + 1], vols[t - 64:t + 1])
            if not r or not r["setup"]:
                continue
            if t - last < args.cooldown:
                continue
            last = t
            n_sig += 1
            for h in HORIZONS:
                res[r["scenario"]][h].append((closes[t + h] / closes[t] - 1) * 100)

    def st(a):
        if not a:
            return (0, 0.0, 0.0, 0.0)
        return (len(a), sum(1 for x in a if x > 0) / len(a) * 100, mean(a), median(a))

    print(f"2560戰法回測  期間 {args.start}~now  冷卻{args.cooldown}日  股票{n_stocks}檔  訊號{n_sig:,}筆")
    print(f"{'情境':<6}{'H':>4}{'n':>7}{'勝率%':>8}{'均報酬%':>9}{'中位%':>8}{'贏基準?':>9}")
    print("-" * 55)
    for h in HORIZONS:
        bn, bw, ba, bm = st(base[h])
        for sc in ("縮量", "做量", "衝量", "誘惑"):
            n, w, a, m = st(res[sc][h])
            edge = f"{a - ba:+.2f}" if n else "—"
            print(f"{sc:<6}{h:>4}{n:>7}{w:>7.1f}{a:>9.2f}{m:>8.2f}{edge:>9}")
        print(f"{'[基準]':<6}{h:>4}{bn:>7}{bw:>7.1f}{ba:>9.2f}{bm:>8.2f}{'—':>9}")
        print("-" * 55)
    print("勝率=前瞻報酬>0比例;贏基準=均報酬減同期任意進場基準均報酬(>0=有超額)。")


if __name__ == "__main__":
    main()
