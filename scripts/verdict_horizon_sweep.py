#!/usr/bin/env python3
"""verdict 持有期掃描 —— 診斷買/賣訊號在不同持有期的表現（絕對 + 市場相對）。

回答「買進 18% 是真爛，還是被 20 日尺度冤枉」：對 5/10/20/40/60/120 日各持有期，
取「約 H 日前」的 verdict 評估到現價，比對全市場母體基準，算絕對與超額命中率。

用法（唯讀，不寫入）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/verdict_horizon_sweep.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit.verdict_tracker import excess_return, forward_return, normalize_verdict  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE, COLL_TEAM_ANALYSIS  # noqa: E402

HORIZONS = [5, 10, 20, 40, 60, 120]
BAND = 0.03


def _f(c):
    return float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)


def _close_latest(db, sym):
    d = db[COLL_STOCK_PRICE].find_one({"symbol": sym}, {"close": 1}, sort=[("date", -1)])
    return _f(d.get("close")) if d else None


def _close_on_or_before(db, sym, date):
    d = db[COLL_STOCK_PRICE].find_one({"symbol": sym, "date": {"$lte": date}},
                                      {"close": 1}, sort=[("date", -1)])
    return _f(d.get("close")) if d else None


def _bucket_stats(rets, market_avg):
    n = len(rets)
    if n == 0:
        return dict(n=0, avg=None, hit=None, exc_avg=None, exc_hit=None)
    avg = sum(rets) / n
    hit = sum(1 for x in rets if x > BAND) / n
    exc = [excess_return(x, market_avg) for x in rets]
    exc_avg = sum(exc) / n
    return dict(n=n, avg=avg, hit=hit, exc_avg=exc_avg)


def main():
    db = get_db()
    now = datetime.now()
    universe = [d["_id"] for d in db[COLL_STOCK_PRICE].aggregate(
        [{"$group": {"_id": "$symbol"}}, {"$limit": 900}])]

    print(f"verdict 持有期掃描 @ {now:%Y-%m-%d}（BAND=±{BAND:.0%}，母體≈{len(universe)}檔）")
    print(f"{'持有期':>5} | {'票別':<4} {'n':>5} {'均報酬':>8} {'命中>+3%':>8} {'超額(vs市場)':>11}")
    print("-" * 60)

    for H in HORIZONS:
        target = now - timedelta(days=H)
        lo, hi = target - timedelta(days=5), target + timedelta(days=5)
        # 市場母體：H 日前→現價
        mret = []
        for s in universe:
            cur = _close_latest(db, s)
            past = _close_on_or_before(db, s, hi)
            r = forward_return(past, cur) if (cur and past) else None
            if r is not None:
                mret.append(r)
        market_avg = sum(mret) / len(mret) if mret else 0.0
        market_hit = sum(1 for x in mret if x > BAND) / len(mret) if mret else 0.0

        recs = list(db[COLL_TEAM_ANALYSIS].find(
            {"date": {"$gte": lo, "$lte": hi}, "final_verdict": {"$exists": True},
             "price_at_analysis": {"$ne": None}},
            {"symbol": 1, "final_verdict": 1, "price_at_analysis": 1}))
        buckets = {"買進": [], "賣出": [], "持有": []}
        for r in recs:
            later = _close_latest(db, r["symbol"])
            ret = forward_return(_f(r.get("price_at_analysis")), later) if later else None
            if ret is not None:
                buckets[normalize_verdict(r["final_verdict"])].append(ret)

        print(f"{H:>4}日 | {'市場':<4} {len(mret):>5} {market_avg:>+7.2%} {market_hit:>7.1%} {'—':>11}")
        for v in ("買進", "賣出", "持有"):
            s = _bucket_stats(buckets[v], market_avg)
            if s["n"] == 0:
                print(f"{'':>5} | {v:<4} {0:>5} {'—':>8} {'—':>8} {'—':>11}")
            else:
                mark = " ✅" if (v == "買進" and s["exc_avg"] > 0) else (" 🔴" if v == "買進" and s["exc_avg"] < 0 else "")
                print(f"{'':>5} | {v:<4} {s['n']:>5} {s['avg']:>+7.2%} {s['hit']:>7.1%} {s['exc_avg']:>+10.2%}{mark}")
        print("-" * 60)


if __name__ == "__main__":
    main()
