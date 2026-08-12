#!/usr/bin/env python3
"""補 fundamental_factors 缺失的 equity/total_assets,並重算 roe/roa/debt_ratio。

背景(2026-08-12 跑 IC 分析時發現):
    fundamental_factors.roe/roa 在 2016Q4、2017Q3~2019Q2 共 8 季幾乎全空
    (2018Q2 共 1769 筆,roe 非空僅 6 筆)。根因是同期 equity / total_assets
    沒有值 —— roe = net_income_ttm / equity,分母缺就整欄 null。損益表側的
    net_income_ttm / revenue_ttm / op_margin 都正常。

    build_fundamental_factors.py 有 `if not eq or not ta: continue`,不可能
    寫出 equity=null 的列,所以這些列是後來補欄位的腳本建的;當時 FinMind
    的 TaiwanStockBalanceSheet 沒給到 Equity,就留下了空欄。

    但原始資料還在:balance_sheet_detail(sync_financial_detail.py 收的)
    在那 8 季各有 1625~1758 檔的 Equity 與 TotalAssets。屬計算缺口,可重算。

作法:
    找 equity 為空、但 net_income_ttm 有值的列 → 從 balance_sheet_detail 取
    Equity / TotalAssets / Liabilities → 回填並重算 roe / roa / debt_ratio。
    只補空值,不覆蓋既有數字(既有值可能已 winsorize 過)。

⚠ balance_sheet_detail.date 是 **Date 型別**(不是字串)。用字串查會靜默回 0 筆
   而讓人以為「沒有原始資料」。相關:date-field-three-representations 的教訓。

用法:
    python3 scripts/backfill_fundamental_equity.py            # dry-run,只報告
    python3 scripts/backfill_fundamental_equity.py --apply    # 實際寫入
    python3 scripts/backfill_fundamental_equity.py --apply --limit 100   # 小批試

寫入後建議接著跑 scripts/winsorize_fundamental.py(idempotent),讓新補的
roe/roa 與既有資料套用同一套離群值處理。
"""
import argparse
from datetime import datetime

from pymongo import MongoClient, UpdateOne

DB_URI = "mongodb://localhost:27017/"
DB_NAME = "tw_stock_analysis"
BATCH = 500

# 與 build_fundamental_factors.py 相同的優先序:合併權益優先,取不到才用母公司業主權益
EQUITY_TYPES = ("Equity", "EquityAttributableToOwnersOfParent")


def balance_lookup(db, period_end, stock_ids):
    """一次撈整期的資產負債欄位,避免逐檔查(N+1)。

    回傳 {stock_id: {"equity":…, "total_assets":…, "liabilities":…}}
    """
    want = set(EQUITY_TYPES) | {"TotalAssets", "Liabilities"}
    cur = db.balance_sheet_detail.find(
        {"date": period_end, "stock_id": {"$in": list(stock_ids)},
         "type": {"$in": list(want)}, "value": {"$ne": None}},
        {"stock_id": 1, "type": 1, "value": 1, "_id": 0},
    )
    raw = {}
    for r in cur:
        raw.setdefault(str(r["stock_id"]), {})[r["type"]] = r["value"]
    out = {}
    for sid, m in raw.items():
        eq = next((m[t] for t in EQUITY_TYPES if m.get(t)), None)
        out[sid] = {"equity": eq, "total_assets": m.get("TotalAssets"),
                    "liabilities": m.get("Liabilities")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="實際寫入(預設只 dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="最多處理幾筆(試跑用)")
    args = ap.parse_args()

    db = MongoClient(DB_URI)[DB_NAME]

    # 安全網:改資料層前後都拍筆數快照
    before = {
        "total": db.fundamental_factors.count_documents({}),
        "roe": db.fundamental_factors.count_documents({"roe": {"$ne": None}}),
        "roa": db.fundamental_factors.count_documents({"roa": {"$ne": None}}),
        "equity": db.fundamental_factors.count_documents({"equity": {"$ne": None}}),
    }
    print(f"[{datetime.now():%H:%M:%S}] 事前快照:{before}")

    # 目標:分母缺、但分子有 —— 這種才補得起來
    q = {"equity": None, "net_income_ttm": {"$ne": None}}
    targets = list(db.fundamental_factors.find(
        q, {"stock_id": 1, "period_end": 1, "net_income_ttm": 1}))
    if args.limit:
        targets = targets[:args.limit]
    print(f"待補列數:{len(targets)}")
    if not targets:
        print("沒有可補的列,結束。")
        return

    by_period = {}
    for t in targets:
        by_period.setdefault(t["period_end"], []).append(t)
    print(f"橫跨 {len(by_period)} 個財季:"
          f"{min(by_period):%Y-%m-%d} ~ {max(by_period):%Y-%m-%d}")

    ops, stats = [], {"filled": 0, "no_balance": 0, "bad_equity": 0}
    for pe in sorted(by_period):
        rows = by_period[pe]
        bmap = balance_lookup(db, pe, {str(r["stock_id"]) for r in rows})
        hit = 0
        for r in rows:
            b = bmap.get(str(r["stock_id"]))
            if not b or not b.get("equity") or not b.get("total_assets"):
                stats["no_balance"] += 1
                continue
            eq, ta, li = b["equity"], b["total_assets"], b.get("liabilities")
            if eq == 0:                      # 分母為 0 → roe 無意義,不硬算
                stats["bad_equity"] += 1
                continue
            ni = r["net_income_ttm"]
            upd = {"equity": eq, "total_assets": ta,
                   "roe": ni / eq * 100, "roa": ni / ta * 100,
                   "backfilled_equity_at": datetime.now(),
                   "backfilled_equity_src": "balance_sheet_detail"}
            if li is not None:
                upd["debt_ratio"] = li / ta * 100
            ops.append(UpdateOne({"_id": r["_id"]}, {"$set": upd}))
            stats["filled"] += 1
            hit += 1
        print(f"  {pe:%Y-%m-%d}: {len(rows)} 筆待補 → 可補 {hit}")

    print(f"\n合計:可補 {stats['filled']}、查無資產負債 {stats['no_balance']}、"
          f"權益為 0 {stats['bad_equity']}")

    if not args.apply:
        print("\n(dry-run,未寫入。加 --apply 才會實際更新)")
        return

    written = 0
    for i in range(0, len(ops), BATCH):
        res = db.fundamental_factors.bulk_write(ops[i:i + BATCH], ordered=False)
        written += res.modified_count
        print(f"  已寫入 {written}/{len(ops)}")

    after = {
        "total": db.fundamental_factors.count_documents({}),
        "roe": db.fundamental_factors.count_documents({"roe": {"$ne": None}}),
        "roa": db.fundamental_factors.count_documents({"roa": {"$ne": None}}),
        "equity": db.fundamental_factors.count_documents({"equity": {"$ne": None}}),
    }
    print(f"[{datetime.now():%H:%M:%S}] 事後快照:{after}")
    print("差異:" + ", ".join(f"{k} {after[k] - before[k]:+d}" for k in before))
    if after["total"] != before["total"]:
        print("🔴 總筆數變了!本腳本只該 $set 既有列,不該新增/刪除,請查。")
    print("\n建議接著跑:python3 scripts/winsorize_fundamental.py"
          "(idempotent,讓新補的 roe/roa 與既有資料套同一套離群值處理)")


if __name__ == "__main__":
    main()
