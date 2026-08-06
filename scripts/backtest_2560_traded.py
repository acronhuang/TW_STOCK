#!/usr/bin/env python3
"""2560戰法「交易式」回測 —— 做量/縮量進場 + 停損/移動停損/讓獲利奔跑。

固定持有期回測(backtest_2560.py)對「賺大賠小」型戰法不公平;本檔模擬真實出場規則:
  進場=訊號當日收盤 → 每日檢查:
    停損(從進場價跌 stop%)/ 移動停損(從波段高點回落 trail%)/ 到期(maxhold日)
  出場後記錄該筆交易報酬、天數、出場原因。
關鍵指標:勝率、平均獲利 vs 平均虧損(**賺賠比**)、**期望值**,對照「任意日進場+同規則」基準。
還原價(adj_close)模擬,除權息不算跌。訊號無未來函數,冷卻期避免重複。

用法: backtest_2560_traded.py [--start 2024-01-01] [--stop 8] [--trail 12] [--maxhold 60] [--cooldown 10]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient

from src.analysis.strategy_2560 import classify_2560
from src.backtesting.tw_costs import roundtrip_pct


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def simulate(closes, i0, stop, trail, maxhold):
    entry = closes[i0]
    peak = entry
    for d in range(1, maxhold + 1):
        i = i0 + d
        if i >= len(closes):
            return (closes[-1] / entry - 1) * 100, i - i0, "資料盡"
        px = closes[i]
        peak = max(peak, px)
        if px <= entry * (1 - stop / 100):
            return (px / entry - 1) * 100, d, "停損"
        if px <= peak * (1 - trail / 100):
            return (px / entry - 1) * 100, d, "移動停損"
    i = min(i0 + maxhold, len(closes) - 1)
    return (closes[i] / entry - 1) * 100, i - i0, "到期"


def stats(trades):
    if not trades:
        return None
    rets = [t[0] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    win_rate = len(wins) / len(rets) * 100
    avg_win = mean(wins) if wins else 0.0
    avg_loss = mean(losses) if losses else 0.0
    exp = mean(rets)                      # 期望值/每筆
    rr = (avg_win / abs(avg_loss)) if avg_loss else float("inf")
    return {"n": len(rets), "win%": win_rate, "avg%": exp, "avg_win%": avg_win,
            "avg_loss%": avg_loss, "賺賠比": rr, "med%": median(rets),
            "avg_days": mean([t[1] for t in trades])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--stop", type=float, default=8.0)
    ap.add_argument("--trail", type=float, default=12.0)
    ap.add_argument("--maxhold", type=int, default=60)
    ap.add_argument("--cooldown", type=int, default=10)
    ap.add_argument("--discount", type=float, default=1.0, help="券商手續費折數(1.0=無折)")
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    args = ap.parse_args()
    rt = roundtrip_pct(args.discount)   # 來回交易成本%
    db = MongoClient(args.uri)["tw_stock_analysis"]
    start = datetime.strptime(args.start, "%Y-%m-%d")
    warm = start - timedelta(days=220)

    ser = defaultdict(list)
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

    trades = defaultdict(list)   # scenario -> [(ret, days, reason)]
    base = []
    for s, bars in ser.items():
        if len(bars) < 90:
            continue
        dates = [b[0] for b in bars]
        closes = [b[1] for b in bars]
        vols = [b[2] for b in bars]
        last = -999
        for t in range(64, len(closes) - 2):
            if dates[t] < start:
                continue
            if t % 20 == 0:      # 基準:每20交易日一筆任意進場(同出場規則)
                base.append(simulate(closes, t, args.stop, args.trail, args.maxhold))
            r = classify_2560(closes[t - 64:t + 1], vols[t - 64:t + 1])
            if not r or not r["setup"]:
                continue
            if t - last < args.cooldown:
                continue
            last = t
            trades[r["scenario"]].append(simulate(closes, t, args.stop, args.trail, args.maxhold))

    print(f"2560交易式回測 {args.start}~now | 停損{args.stop}% 移動停損{args.trail}% 到期{args.maxhold}日 冷卻{args.cooldown} | 來回成本{rt:.3f}%(折{args.discount})")
    hdr = f"{'情境':<6}{'n':>7}{'勝率%':>7}{'期望%':>8}{'期望淨%':>8}{'均獲利%':>8}{'均虧損%':>8}{'賺賠比':>7}{'均天數':>7}"
    print(hdr); print("-" * len(hdr))
    for sc in ("做量", "縮量", "衝量", "誘惑"):
        d = stats(trades[sc])
        if d:
            print(f"{sc:<6}{d['n']:>7}{d['win%']:>7.1f}{d['avg%']:>8.2f}{d['avg%']-rt:>8.2f}{d['avg_win%']:>8.2f}"
                  f"{d['avg_loss%']:>8.2f}{d['賺賠比']:>7.2f}{d['avg_days']:>7.0f}")
    b = stats(base)
    if b:
        print(f"{'[基準]':<6}{b['n']:>7}{b['win%']:>7.1f}{b['avg%']:>8.2f}{b['avg%']-rt:>8.2f}{b['avg_win%']:>8.2f}"
              f"{b['avg_loss%']:>8.2f}{b['賺賠比']:>7.2f}{b['avg_days']:>7.0f}")
    print("-" * len(hdr))
    # 出場原因分布(做量)
    reasons = defaultdict(int)
    for _, _, why in trades["做量"]:
        reasons[why] += 1
    print("做量出場原因:", dict(reasons))
    print(f"期望%=每筆平均毛報酬;期望淨%=扣來回成本{rt:.3f}%後;賺賠比=均獲利/|均虧損|;對照基準看做量扣成本後是否仍有超額。")


if __name__ == "__main__":
    main()
