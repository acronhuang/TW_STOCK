#!/usr/bin/env python3
"""stock_factors 全量重算回填 2013-2019(現況最早 2020-01-02)。

用 production 的 FactorLibrary.calculate_and_store(保證與 2020+ 因子定義一致)。
逐月處理(檢查點/可續跑):已有因子的月份跳過。upsert by (symbol,date) 增量安全。
momentum 需 trailing 價,2013 前期(~12 個月)因無 2012 前價會部分為 None,屬正常。

本地計算,不佔 FinMind 配額。慢(~85s/交易日,全程約 40hr)→ nice 低優先權避免搶日常 pipeline。
中斷後同指令 --resume 續跑。

用法: factor_backfill_2013_2019.py [--from 2013-01] [--to 2019-12] [--resume]
"""
import argparse
import sys
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from pymongo import MongoClient
from src.factors.factor_calculator import FactorLibrary


def month_iter(frm, to):
    y, m = map(int, frm.split("-"))
    ey, em = map(int, to.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m = 1; y += 1


def month_bounds(y, m):
    start = datetime(y, m, 1)
    nxt = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    return start, nxt   # nxt = 次月1日(exclusive 上界)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2013-01")
    ap.add_argument("--to", dest="to", default="2019-12")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    fl = FactorLibrary()

    months = list(month_iter(args.frm, args.to))
    print(f"回填 stock_factors {args.frm}~{args.to},共 {len(months)} 個月", flush=True)
    grand = 0
    for idx, (y, m) in enumerate(months, 1):
        start, nxt = month_bounds(y, m)
        last = nxt - timedelta(days=1)   # 當月最後一天(calculate_and_store 的 end 為 $lte)
        # 該月股票池(有價者)
        syms = sorted(s for s in db.stock_price.distinct("stock_id",
                      {"date": {"$gte": start, "$lt": nxt}})
                      if isinstance(s, str) and len(s) == 4 and s.isdigit())
        if not syms:
            print(f"[{y}-{m:02d}] 無股票池,跳過", flush=True); continue
        # resume:該月已有因子(達股票池×交易日 7 成)則跳過
        have = db.stock_factors.count_documents({"date": {"$gte": start, "$lt": nxt}})
        tdays = len(db.stock_price.distinct("date", {"date": {"$gte": start, "$lt": nxt}}))
        if args.resume and tdays and have >= len(syms) * tdays * 0.7:
            print(f"[{y}-{m:02d}] 已有 {have} 因子(≈{len(syms)}×{tdays}),跳過", flush=True)
            continue
        t0 = time.time()
        stats = fl.calculate_and_store(syms, start.strftime("%Y-%m-%d"),
                                       last.strftime("%Y-%m-%d"))
        dt = time.time() - t0
        grand += stats.get("inserted", 0) + stats.get("updated", 0)
        print(f"[{y}-{m:02d}] {len(syms)}檔×{tdays}日 → ins{stats.get('inserted',0)} upd{stats.get('updated',0)} "
              f"fail{stats.get('failed',0)}  {dt:.0f}s  (進度 {idx}/{len(months)}, 累計{grand:,})", flush=True)

    print(f"\n完成:stock_factors 回填累計 {grand:,} 筆寫入", flush=True)
    print("⚠️ 建議接著跑 backfill_pe_pb_factors.py 補 pb_ratio(若 value_factors 未含)", flush=True)


if __name__ == "__main__":
    main()
