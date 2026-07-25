#!/usr/bin/env python3
"""大戶持股 > 55% + 量價多空勢 篩選

多方勢:上漲日均量 > 下跌日均量(上漲有量、下跌量縮)
空方勢:上漲日均量 < 下跌日均量(上漲量縮、下跌有量)
"""
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from decimal import Decimal

from pymongo import MongoClient

UTC = timezone.utc


def d(x):
    """Decimal128 / int / float -> float"""
    if x is None:
        return None
    try:
        return float(x.to_decimal()) if hasattr(x, "to_decimal") else float(x)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holder-min", type=float, default=55.0, help="大戶持股比例下限 (%%)")
    ap.add_argument("--field", default="big400_pct",
                    choices=["big400_pct", "big_pct"], help="大戶欄位")
    ap.add_argument("--window", type=int, default=20, help="量價觀察交易日數")
    ap.add_argument("--ratio", type=float, default=1.2,
                    help="多方勢門檻:上漲均量/下跌均量")
    ap.add_argument("--bear", action="store_true", help="改列空方勢")
    ap.add_argument("--min-turnover", type=float, default=1e7,
                    help="近月日均成交金額下限(過濾冷門股)")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017").tw_stock_analysis

    # ---- 1. 大戶持股(取最新一期 TDCC) ----
    latest = db.shareholding.find_one(sort=[("date", -1)])["date"]
    holders = {
        r["stock_id"]: r
        for r in db.shareholding.find(
            {"date": latest, args.field: {"$gt": args.holder_min}},
            {"stock_id": 1, "big400_pct": 1, "big_pct": 1, "big_holders": 1},
        )
        # 只留普通股 4 碼、非 00 開頭(排除 ETF/受益憑證/權證)
        if len(r["stock_id"]) == 4 and not r["stock_id"].startswith("00")
    }
    print(f"[大戶] {latest:%Y-%m-%d} {args.field} > {args.holder_min}% -> {len(holders)} 檔普通股")
    if not holders:
        return

    # ---- 2. 量價:近 window 交易日 ----
    price_latest = db.stock_price.find_one(sort=[("date", -1)])["date"]
    since = price_latest - timedelta(days=int(args.window * 1.9) + 10)

    rows = db.stock_price.find(
        {"stock_id": {"$in": list(holders)}, "date": {"$gte": since}},
        {"_id": 0, "stock_id": 1, "date": 1, "close": 1, "volume": 1,
         "name": 1, "Trading_money": 1, "amount": 1},
    ).sort([("stock_id", 1), ("date", 1)])

    series = defaultdict(list)
    for r in rows:
        c, v = d(r.get("close")), d(r.get("volume"))
        if c and v is not None:
            # 近期資料 Trading_money/amount 多為 None,退回 close*volume 估算
            money = d(r.get("Trading_money")) or d(r.get("amount")) or c * v
            series[r["stock_id"]].append((r["date"], c, v, money, r.get("name")))

    out = []
    for sid, bars in series.items():
        bars = bars[-(args.window + 1):]
        if len(bars) < args.window // 2:
            continue  # 資料太少,不判斷

        turnover = sum(b[3] for b in bars) / len(bars)
        if turnover < args.min_turnover:
            continue

        up_v, dn_v = [], []
        for prev, cur in zip(bars, bars[1:]):
            chg = cur[1] - prev[1]
            if chg > 0:
                up_v.append(cur[2])
            elif chg < 0:
                dn_v.append(cur[2])
        if not up_v or not dn_v:
            continue  # 單邊行情,量能比無意義

        au, ad = sum(up_v) / len(up_v), sum(dn_v) / len(dn_v)
        ratio = au / ad if ad else float("inf")

        bull = ratio >= args.ratio
        bear = ratio <= 1 / args.ratio
        if (args.bear and not bear) or (not args.bear and not bull):
            continue

        h = holders[sid]
        out.append({
            "stock_id": sid,
            "name": bars[-1][4] or "",
            "big400_pct": h.get("big400_pct"),
            "big_pct": h.get("big_pct"),
            "ratio": ratio,
            "close": bars[-1][1],
            "ret": (bars[-1][1] / bars[0][1] - 1) * 100,
            "turnover": turnover,
        })

    out.sort(key=lambda r: r["ratio"], reverse=not args.bear)
    label = "空方勢" if args.bear else "多方勢"
    print(f"[量價] 近 {args.window} 交易日({price_latest:%Y-%m-%d} 止){label} -> {len(out)} 檔\n")

    print(f"{'代號':<6}{'名稱':<10}{'大戶%':>7}{'量能比':>8}{'收盤':>9}{'期間%':>8}{'日均額(億)':>11}")
    print("-" * 60)
    for r in out:
        print(f"{r['stock_id']:<6}{r['name']:<10}{r['big400_pct']:>7.1f}"
              f"{r['ratio']:>8.2f}{r['close']:>9.2f}{r['ret']:>8.1f}"
              f"{r['turnover']/1e8:>11.2f}")


if __name__ == "__main__":
    main()
