"""清除防呆後不再產生的舊 factor。

build_adjustment_factors.py 只做 upsert,不會刪除。加入「prev_close 距離」防呆後,
先前用跨年錯誤鄰居算出的 factor 仍留在 adjustment_factors 裡,
backfill_adj_close 還是會把它們乘進累積係數 —— 必須刪掉。
"""
import argparse
import sys

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
from pymongo import MongoClient
from build_adjustment_factors import build_events, price_lookup, compute

ap = argparse.ArgumentParser()
ap.add_argument("--delete", action="store_true", help="實際刪除(預設只列出)")
args = ap.parse_args()

db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

events = build_events(db, 100.0)          # 現增率除以 100(已定案)
series = price_lookup(db, events)
rows, _, skip = compute(events, series)
valid = {(r["stock_id"], r["ex_date"]) for r in rows}
print(f"防呆後有效事件: {len(valid):,}")
print(f"跳過統計: {skip}")

cur = [(d["stock_id"], d["ex_date"]) for d in
       db.adjustment_factors.find({}, {"_id": 0, "stock_id": 1, "ex_date": 1})]
stale = [k for k in cur if k not in valid]
print(f"庫內共 {len(cur):,} 筆,其中已失效 {len(stale):,} 筆")

if stale[:5]:
    print("\n樣本:")
    for sid, ex in stale[:5]:
        d = db.adjustment_factors.find_one({"stock_id": sid, "ex_date": ex})
        print(f"  {sid} {ex:%Y-%m-%d}  prev_close={d.get('prev_close')}  factor={d.get('factor')}")

if not args.delete:
    print("\n(未加 --delete,不刪除)")
else:
    n = 0
    for sid, ex in stale:
        n += db.adjustment_factors.delete_one({"stock_id": sid, "ex_date": ex}).deleted_count
    print(f"\n已刪除 {n:,} 筆;剩餘 {db.adjustment_factors.count_documents({}):,} 筆")
