#!/usr/bin/env python3
"""verdict 多窗回測 —— 跨多個評估日/市場情境驗證買賣訊號是否「結構性做反」。

單一評估點無法區分「選股結構性做反」與「這波行情剛好不利」。本腳本固定持有期，
把評估結束日 R 往回掃多點（涵蓋多空情境），看買進超額報酬是否在「所有情境」皆負
（→結構性問題）還是「僅上漲情境」為負（→情境問題，模型未必要改）。

用法（唯讀，不寫入）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/verdict_multiwindow_backtest.py --horizon 20
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit.verdict_tracker import forward_return, normalize_verdict  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE, COLL_TEAM_ANALYSIS  # noqa: E402

BAND = 0.03


def _f(c):
    return float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)


def _close_on_or_before(db, sym, date):
    d = db[COLL_STOCK_PRICE].find_one({"symbol": sym, "date": {"$lte": date}},
                                      {"close": 1}, sort=[("date", -1)])
    return _f(d.get("close")) if d else None


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=20, help="持有期（日曆天）")
    ap.add_argument("--step", type=int, default=20, help="評估日回掃間隔")
    ap.add_argument("--points", type=int, default=8, help="評估點數")
    ap.add_argument("--universe", type=int, default=500, help="市場母體抽樣數")
    args = ap.parse_args()

    db = get_db()
    H = args.horizon
    now = datetime.now()
    universe = [d["_id"] for d in db[COLL_STOCK_PRICE].aggregate(
        [{"$group": {"_id": "$symbol"}}, {"$limit": args.universe}])]

    print(f"多窗回測：持有期={H}日，母體≈{len(universe)}檔，BAND=±{BAND:.0%}")
    print(f"{'評估結束日R':>12} | {'市場':>7} | {'買進超額':>9} {'n':>4} | {'賣出超額':>9} {'n':>4} | 情境")
    print("-" * 78)

    buy_all_neg = True
    buy_excess_by_regime = {"up": [], "down": []}

    for i in range(1, args.points + 1):
        R = now - timedelta(days=H + args.step * i)   # 評估結束日（留 H 天讓母體有後價）
        entry_date = R - timedelta(days=H)
        lo, hi = entry_date - timedelta(days=5), entry_date + timedelta(days=5)

        # 市場母體：entry_date → R
        mret = []
        for s in universe:
            e = _close_on_or_before(db, s, hi)
            later = _close_on_or_before(db, s, R)
            r = forward_return(e, later) if (e and later) else None
            if r is not None:
                mret.append(r)
        market_avg = _avg(mret) or 0.0

        recs = list(db[COLL_TEAM_ANALYSIS].find(
            {"date": {"$gte": lo, "$lte": hi}, "final_verdict": {"$exists": True},
             "price_at_analysis": {"$ne": None}},
            {"symbol": 1, "final_verdict": 1, "price_at_analysis": 1}))
        buckets = {"買進": [], "賣出": [], "持有": []}
        for r in recs:
            later = _close_on_or_before(db, r["symbol"], R)
            ret = forward_return(_f(r.get("price_at_analysis")), later) if later else None
            if ret is not None:
                buckets[normalize_verdict(r["final_verdict"])].append(ret)

        b_avg, s_avg = _avg(buckets["買進"]), _avg(buckets["賣出"])
        b_exc = (b_avg - market_avg) if b_avg is not None else None
        s_exc = (s_avg - market_avg) if s_avg is not None else None
        regime = "📈上漲" if market_avg > 0.01 else ("📉下跌" if market_avg < -0.01 else "→ 盤整")

        if b_exc is not None:
            if b_exc >= 0:
                buy_all_neg = False
            (buy_excess_by_regime["up"] if market_avg > 0 else buy_excess_by_regime["down"]).append(b_exc)

        def fmt(x):
            return f"{x:>+8.2%}" if x is not None else f"{'—':>9}"
        print(f"{R:%Y-%m-%d}   | {market_avg:>+6.2%} | {fmt(b_exc)} {len(buckets['買進']):>4} | "
              f"{fmt(s_exc)} {len(buckets['賣出']):>4} | {regime}")

    print("-" * 78)
    up = buy_excess_by_regime["up"]; dn = buy_excess_by_regime["down"]
    print(f"買進超額：上漲情境均值={_avg(up):+.2%}（n={len(up)}）" if up else "買進超額：上漲情境無資料")
    print(f"　　　　　下跌/盤整情境均值={_avg(dn):+.2%}（n={len(dn)}）" if dn else "　　　　　下跌情境無資料")
    print()
    if buy_all_neg and up and dn:
        print("🔴 結論：買進超額在【所有情境】皆為負 → 結構性做反，建議動模型（加動能閘門）。")
    elif up and dn and _avg(up) < 0 <= (_avg(dn) or 0):
        print("🟠 結論：買進僅在【上漲情境】為負、下跌情境不差 → 偏情境（逆勢/太保守），先加情境濾網。")
    else:
        print("🟡 結論：情境混合，需更多評估點；勿在單一情境上過擬合。")


if __name__ == "__main__":
    main()
