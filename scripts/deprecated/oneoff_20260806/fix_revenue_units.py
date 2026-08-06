#!/usr/bin/env python3
"""修 monthly_revenue 單位不一致:FinMind:TaiwanStockMonthRevenue 存的是「元」(×1000 太大),
其餘(TWSE_OpenAPI/FinMind/TPEX_OpenAPI)是正確的「千元」。

作法:
  Phase 1: 把 data_source == 'FinMind:TaiwanStockMonthRevenue' 的金額欄 ÷1000 → 千元,
           並改 data_source 標記 '...(kNTD)' 以冪等(不會重複除)。
  Phase 2: 全表(所有源,已統一千元)按 symbol 重算 yoy_growth/mom_growth(跨單位邊界月被污染,重算最安全)。

用法: fix_revenue_units.py           # dry-run(只看不寫)
      fix_revenue_units.py --execute # 實際寫入
"""
import argparse
from pymongo import MongoClient, UpdateOne

BAD_SRC = "FinMind:TaiwanStockMonthRevenue"          # 元,待修
FIXED_SRC = "FinMind:TaiwanStockMonthRevenue(kNTD)"  # 已正規化標記
MONEY = ["revenue", "last_month_revenue", "cumulative_revenue",
         "last_year_revenue", "last_year_cumulative_revenue"]


def pm(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"


def ly(ym):
    return f"{int(ym[:4])-1}-{ym[5:7]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    args = ap.parse_args()
    db = MongoClient(args.uri)["tw_stock_analysis"]
    mr = db.monthly_revenue

    n_bad = mr.count_documents({"data_source": BAD_SRC})
    print(f"待正規化(元→千元)列數: {n_bad:,}")
    # 抽樣 before/after 示意(台汽電)
    print("台汽電 8926 修前(revenue 原始):")
    for r in mr.find({"symbol": "8926"}).sort("year_month", -1).limit(6):
        print(f"  {r['year_month']}: {r.get('revenue'):>18,.0f}  {r.get('data_source')}")

    if not args.execute:
        print("\n[dry-run] 未寫入。加 --execute 實際修復。")
        return

    # ── Phase 1: ÷1000 + 標記 ──
    print("\nPhase 1: ÷1000 正規化…")
    ops, done = [], 0
    for r in mr.find({"data_source": BAD_SRC}):
        upd = {f: r[f] / 1000 for f in MONEY if isinstance(r.get(f), (int, float)) and r.get(f) is not None}
        upd["data_source"] = FIXED_SRC
        ops.append(UpdateOne({"_id": r["_id"]}, {"$set": upd}))
        if len(ops) >= 2000:
            mr.bulk_write(ops, ordered=False); done += len(ops); ops = []
            print(f"  …{done:,}/{n_bad:,}")
    if ops:
        mr.bulk_write(ops, ordered=False); done += len(ops)
    print(f"  Phase 1 完成: {done:,} 列")

    # ── Phase 2: 全表按 symbol 重算 yoy/mom(統一千元後)──
    print("Phase 2: 重算 yoy/mom…")
    syms = mr.distinct("symbol")
    tot = 0
    for i, sym in enumerate(syms, 1):
        rows = list(mr.find({"symbol": sym}, {"year_month": 1, "revenue": 1}))
        rev = {r["year_month"]: r["revenue"] for r in rows if r.get("revenue")}
        ops = []
        for r in rows:
            ym = r["year_month"]; v = rev.get(ym)
            if not v:
                continue
            mom = round((v / rev[pm(ym)] - 1) * 100, 4) if rev.get(pm(ym)) else None
            yoy = round((v / rev[ly(ym)] - 1) * 100, 4) if rev.get(ly(ym)) else None
            ops.append(UpdateOne({"_id": r["_id"]}, {"$set": {"mom_growth": mom, "yoy_growth": yoy}}))
        if ops:
            mr.bulk_write(ops, ordered=False); tot += len(ops)
        if i % 500 == 0:
            print(f"  …{i}/{len(syms)} 檔")
    print(f"  Phase 2 完成: {tot:,} 列 yoy/mom 已重算")

    print("\n台汽電 8926 修後:")
    for r in mr.find({"symbol": "8926"}).sort("year_month", -1).limit(6):
        print(f"  {r['year_month']}: rev={r.get('revenue'):>14,.0f} 千元  yoy={r.get('yoy_growth')}  mom={r.get('mom_growth')}")


if __name__ == "__main__":
    main()
