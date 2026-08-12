#!/usr/bin/env python3
"""補 fundamental_factors 缺失的 net_income_ttm / revenue_ttm,並重算 roe/roa/profit_margin。

背景(2026-08-12):
    補完 equity 破洞後(backfill_fundamental_equity.py),roe 覆蓋率仍有 3 期
    卡在 79~80%,使 quality_roe_pit 過不了 IC 的 85% 閘門。追下去發現是
    **分子側**缺:net_income_ttm 為 null(全表 5353 筆,各期 60~160 筆)。

    兩個根因:
    1. 欄名不一致:一般產業用 IncomeAfterTaxes(複數),部分金融/保險業用
       IncomeAfterTax(單數)。build_fundamental_factors.py 只取複數
       → 單數那批整條 TTM 算不出來。2024Q2 有 24 檔屬此。
    2. TTM 窗內缺季:financial_statement_detail 在個別股票的歷史中間漏季
       (例 1294 有 16 季但缺 2023-09-30)。這種缺四季湊不齊,只能重抓來源。

    本腳本處理的是「資料其實已在本機、只是沒被算出來」的部分 —— 不打 API。

⚠ 單位自檢:FinMind 損益表為**單季**值,TTM = 近四季加總。腳本啟動時會用
   台積電(2330)2023 年四季合計對照公開年報淨利(約 8,385 億)驗證這個假設,
   偏離超過 15% 就中止 —— 若來源某天改成累計值,加總會嚴重高估而無人察覺。

用法:
    python3 scripts/backfill_fundamental_income.py            # dry-run
    python3 scripts/backfill_fundamental_income.py --apply
"""
import argparse
from datetime import datetime

from pymongo import MongoClient, UpdateOne

DB_URI = "mongodb://localhost:27017/"
DB_NAME = "tw_stock_analysis"
BATCH = 500

NI_TYPES = ("IncomeAfterTaxes", "IncomeAfterTax")   # 複數優先,金融業用單數
REV_TYPES = ("Revenue",)

# 單位自檢基準:台積電 2023 年稅後淨利約 8,385 億元
SANITY = {"stock_id": "2330", "year": 2023, "expect": 838_500_000_000, "tol": 0.15}


def quarters_ending(period_end):
    """回傳以 period_end 為終點的近四個季末(含自身),由舊到新。"""
    out, y, m = [], period_end.year, period_end.month
    for _ in range(4):
        out.append(_qdate(y, m))
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return list(reversed(out))


def _qdate(y, m):
    last = {3: 31, 6: 30, 9: 30, 12: 31}
    return datetime(y, m, last.get(m, 31))


def fetch_series(db, stock_ids, dates, types):
    """{(stock_id, date): value};一次撈完避免 N+1。"""
    cur = db.financial_statement_detail.find(
        {"stock_id": {"$in": list(stock_ids)}, "date": {"$in": list(dates)},
         "type": {"$in": list(types)}, "value": {"$ne": None}},
        {"stock_id": 1, "date": 1, "type": 1, "value": 1, "_id": 0},
    )
    out = {}
    for r in cur:
        k = (str(r["stock_id"]), r["date"])
        # 複數優先:兩者都有時(實測沒有)以複數為準
        if k not in out or r["type"] == NI_TYPES[0]:
            out[k] = r["value"]
    return out


def sanity_check(db):
    """確認來源是單季值而非累計值,否則 TTM 加總會嚴重高估。"""
    qs = [_qdate(SANITY["year"], m) for m in (3, 6, 9, 12)]
    vals = fetch_series(db, [SANITY["stock_id"]], qs, NI_TYPES)
    if len(vals) < 4:
        return None, f"自檢無法進行:{SANITY['stock_id']} {SANITY['year']} 只找到 {len(vals)}/4 季"
    total = sum(vals.values())
    dev = abs(total - SANITY["expect"]) / SANITY["expect"]
    ok = dev <= SANITY["tol"]
    msg = (f"單位自檢:{SANITY['stock_id']} {SANITY['year']} 四季合計 {total:,.0f} "
           f"vs 年報約 {SANITY['expect']:,.0f}(偏離 {dev:.1%})→ "
           f"{'通過,確認為單季值' if ok else '🔴 失敗'}")
    return ok, msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    db = MongoClient(DB_URI)[DB_NAME]

    ok, msg = sanity_check(db)
    print(msg)
    if ok is False:
        print("來源單位假設不成立,中止 —— 硬算會產生看似合理但錯誤的 TTM。")
        return

    before = {
        "total": db.fundamental_factors.count_documents({}),
        "ni": db.fundamental_factors.count_documents({"net_income_ttm": {"$ne": None}}),
        "roe": db.fundamental_factors.count_documents({"roe": {"$ne": None}}),
    }
    print(f"[{datetime.now():%H:%M:%S}] 事前快照:{before}")

    targets = list(db.fundamental_factors.find(
        {"net_income_ttm": None},
        {"stock_id": 1, "period_end": 1, "equity": 1, "total_assets": 1, "revenue_ttm": 1}))
    if args.limit:
        targets = targets[:args.limit]
    print(f"待補列數:{len(targets)}")
    if not targets:
        return

    # 一次撈齊所有需要的 (stock, quarter)
    need_dates, need_ids = set(), set()
    for t in targets:
        need_ids.add(str(t["stock_id"]))
        need_dates.update(quarters_ending(t["period_end"]))
    print(f"需查 {len(need_ids)} 檔 × {len(need_dates)} 個季末")
    ni_map = fetch_series(db, need_ids, need_dates, NI_TYPES)
    rev_map = fetch_series(db, need_ids, need_dates, REV_TYPES)

    ops, stats = [], {"filled": 0, "incomplete": 0, "roe_too": 0}
    for t in targets:
        sid = str(t["stock_id"])
        qs = quarters_ending(t["period_end"])
        vals = [ni_map.get((sid, q)) for q in qs]
        if any(v is None for v in vals):
            stats["incomplete"] += 1        # 四季湊不齊 → 只能重抓來源,本腳本不處理
            continue
        ni = sum(vals)
        upd = {"net_income_ttm": ni,
               "backfilled_income_at": datetime.now(),
               "backfilled_income_src": "financial_statement_detail"}

        rvals = [rev_map.get((sid, q)) for q in qs]
        rev = sum(rvals) if all(v is not None for v in rvals) else t.get("revenue_ttm")
        if rev:
            upd["revenue_ttm"] = rev
            upd["profit_margin"] = ni / rev * 100

        eq, ta = t.get("equity"), t.get("total_assets")
        if eq:
            upd["roe"] = ni / eq * 100
            stats["roe_too"] += 1
        if ta:
            upd["roa"] = ni / ta * 100

        ops.append(UpdateOne({"_id": t["_id"]}, {"$set": upd}))
        stats["filled"] += 1

    print(f"可補 {stats['filled']}(其中 {stats['roe_too']} 筆同時可算出 roe)、"
          f"四季不齊 {stats['incomplete']}")

    if not args.apply:
        print("\n(dry-run,未寫入。加 --apply 才會實際更新)")
        return

    written = 0
    for i in range(0, len(ops), BATCH):
        written += db.fundamental_factors.bulk_write(
            ops[i:i + BATCH], ordered=False).modified_count
    print(f"已寫入 {written}")

    after = {
        "total": db.fundamental_factors.count_documents({}),
        "ni": db.fundamental_factors.count_documents({"net_income_ttm": {"$ne": None}}),
        "roe": db.fundamental_factors.count_documents({"roe": {"$ne": None}}),
    }
    print(f"[{datetime.now():%H:%M:%S}] 事後快照:{after}")
    print("差異:" + ", ".join(f"{k} {after[k] - before[k]:+d}" for k in before))
    if after["total"] != before["total"]:
        print("🔴 總筆數變了!本腳本只該 $set,請查。")


if __name__ == "__main__":
    main()
