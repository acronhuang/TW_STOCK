#!/usr/bin/env python3
"""用 adjustment_factors 回填 stock_price.adj_close / adjustment_factor(後復權)。

定義(寫死在這裡,下游請照這個解讀):
    adjustment_factor[t] = 所有 ex_date > t 的事件 factor 連乘   (最新日 = 1.0)
    adj_close[t]         = close[t] × adjustment_factor[t]

亦即「後復權」:最新價維持原值,歷史價等比壓低,報酬率連續。
⚠️ 後復權價不是當日真實成交價 —— 拿來算報酬正確,拿來當絕對金額要知道是還原幣值。

效率:累積係數只在除權息日變動,故每檔切成 N+1 個日期區段,
每段一次 updateMany + aggregation pipeline 讓 MongoDB 自己算乘法。
510 萬筆 → 約 1.7 萬次操作。

用法:
    python3 scripts/backfill_adj_close.py --stock-id 2330 --dry-run
    python3 scripts/backfill_adj_close.py --execute
"""
import argparse
from datetime import datetime, timedelta
from decimal import Decimal

from bson.decimal128 import Decimal128
from pymongo import MongoClient

STATE = "adj_close_backfill_state"


def f(x):
    if x is None:
        return 0.0
    try:
        return float(x.to_decimal()) if hasattr(x, "to_decimal") else float(x)
    except (TypeError, ValueError):
        return 0.0


def segments(events):
    """events: [(ex_date, factor)] 已按日期升冪。回傳 [(lo, hi, cum)],hi 為開區間上界(None=無限)"""
    n = len(events)
    # suffix[i] = f_i * f_{i+1} * ... * f_{n-1}
    suffix = [1.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] * events[i][1]

    segs = []
    lo = None
    for i, (ex, _) in enumerate(events):
        segs.append((lo, ex, suffix[i]))   # [lo, ex) 的價格要乘 suffix[i]
        lo = ex
    segs.append((lo, None, 1.0))           # 最後一個除權息日(含)之後 = 1.0
    return segs


def process(db, sid, dry_run):
    evs = [(r["ex_date"], f(r["factor"]))
           for r in db.adjustment_factors.find(
               {"stock_id": sid}, {"_id": 0, "ex_date": 1, "factor": 1}).sort("ex_date", 1)]
    evs = [(d, x) for d, x in evs if 0 < x < 1.5]   # 防呆:factor 應 <1,異常值不套用

    modified = 0
    for lo, hi, cum in segments(evs):
        q = {"stock_id": sid}
        rng = {}
        if lo is not None:
            rng["$gte"] = lo
        if hi is not None:
            rng["$lt"] = hi
        if rng:
            q["date"] = rng
        if dry_run:
            continue
        cum128 = Decimal128(Decimal(repr(cum)))
        sets = {"adjustment_factor": cum128}
        # OHLC 四個欄位都要還原 —— 只還原 close 會讓還原價對上未還原的 open/high/low
        for src, dst in (("close", "adj_close"), ("open", "adj_open"),
                         ("high", "adj_high"), ("low", "adj_low")):
            sets[dst] = {"$cond": [
                {"$in": [{"$type": f"${src}"}, ["missing", "null"]]}, None,
                {"$multiply": [{"$toDecimal": f"${src}"}, cum128]}]}
        res = db.stock_price.update_many(q, [{"$set": sets}])
        modified += res.modified_count
    return len(evs), modified


def preview(db, sid):
    evs = [(r["ex_date"], f(r["factor"]))
           for r in db.adjustment_factors.find({"stock_id": sid}).sort("ex_date", 1)]
    evs = [(d, x) for d, x in evs if 0 < x < 1.5]
    segs = segments(evs)
    print(f"{sid}: {len(evs)} 個除權息事件 → {len(segs)} 個區段")
    print(f"\n{'區段起':<12}{'區段迄':<12}{'累積係數':>12}")
    print("-" * 38)
    for lo, hi, cum in segs[:6]:
        print(f"{(lo.strftime('%Y-%m-%d') if lo else '(最早)'):<12}"
              f"{(hi.strftime('%Y-%m-%d') if hi else '(至今)'):<12}{cum:>12.6f}")
    if len(segs) > 6:
        print(f"  … 省略 {len(segs)-6} 段")

    print(f"\n{'日期':<12}{'現 close':>10}{'現 adj_close':>13}{'回填後 adj':>12}{'累積係數':>11}")
    print("-" * 60)
    for lo, hi, cum in [segs[0], segs[len(segs) // 2], segs[-1]]:
        q = {"stock_id": sid}
        rng = {}
        if lo is not None:
            rng["$gte"] = lo
        if hi is not None:
            rng["$lt"] = hi
        if rng:
            q["date"] = rng
        d = db.stock_price.find_one(q, sort=[("date", -1)])
        if not d:
            continue
        c = f(d.get("close"))
        print(f"{d['date']:%Y-%m-%d}  {c:>10.2f}{f(d.get('adj_close')):>13.2f}"
              f"{c*cum:>12.2f}{cum:>11.6f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--resume", action="store_true", help="跳過已完成的股票")
    ap.add_argument("--changed-only", action="store_true",
                    help="只重算 adjustment_factors 近期有異動的股票(每日 cron 用)")
    ap.add_argument("--days", type=int, default=3, help="--changed-only 的回看天數")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

    if args.stock_id:
        if args.execute:
            n, m = process(db, args.stock_id, False)
            print(f"{args.stock_id}: {n} 事件, 更新 {m:,} 筆")
        else:
            preview(db, args.stock_id)
        return

    if not args.execute:
        print("全量模式需要 --execute(或用 --stock-id ... 預覽單檔)")
        return

    done = set()
    if args.resume:
        done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
        print(f"續跑:已完成 {len(done)} 檔")

    ids = sorted(db.stock_price.distinct("stock_id"))

    if args.changed_only:
        # 兩種都要重算:
        # (1) 有新除權息事件 → 該檔「所有歷史列」的累積係數都變了
        # (2) 有任何一列缺 adjustment_factor → 每日新進的資料列,下載器只寫 close/adj_close,
        #     不會產生 adj_open/high/low/adjustment_factor。若只看 (1),沒有新事件的個股
        #     就永遠補不到這些欄位,每天累積約 5,600 筆缺漏。
        cut = datetime.now() - timedelta(days=args.days)
        changed = set(db.adjustment_factors.distinct("stock_id", {"updated_at": {"$gte": cut}}))
        missing = set(db.stock_price.distinct("stock_id", {"adjustment_factor": None}))
        want = changed | missing
        ids = [s for s in ids if s in want]
        print(f"增量模式:除權息異動 {len(changed):,} 檔 + 缺還原欄位 {len(missing):,} 檔 "
              f"→ 待處理 {len(ids):,} 檔")
        if not ids:
            print("無異動,結束。")
            return
        done = set()   # 增量模式下 state 不該擋掉重算

    todo = [s for s in ids if s not in done]
    print(f"待處理 {len(todo):,} 檔")

    tot_mod = 0
    for i, sid in enumerate(todo, 1):
        try:
            n, m = process(db, sid, False)
            tot_mod += m
            db[STATE].update_one({"stock_id": sid},
                                 {"$set": {"events": n, "modified": m, "at": datetime.now()}},
                                 upsert=True)
        except Exception as e:
            print(f"  ! {sid}: {e}")
        if i % 500 == 0:
            print(f"  … {i:,}/{len(todo):,}  累計更新 {tot_mod:,} 筆")

    print(f"\n完成:更新 {tot_mod:,} 筆")


if __name__ == "__main__":
    main()
