#!/usr/bin/env python3
"""重建品質因子時間序列(roe/roa/profit_margin/debt_ratio),帶正確的公告落後。

背景:stock_factors 裡的 quality 四個因子是**常數** —— 把近期財報回頭貼到 2020 年起的每一天,
是純前視偏誤。2026-07-20 實測,光這一項就讓 v21 年化虛增約 15 個百分點。

作法:
  1. FinMind TaiwanStockFinancialStatements + TaiwanStockBalanceSheet(免費層可用)
  2. 損益表數字為「單季」,故 TTM 指標取近四季加總
  3. available_from = 台股法定公告期限(保守):
       Q1(03-31)→05-15   Q2(06-30)→08-14   Q3(09-30)→11-14   Q4(12-31)→次年 03-31
     刻意用法定期限而非實際公告日 —— 寧可晚知道,不可早知道。

寫入 `fundamental_factors`,不動 stock_factors(套用是下一步,分開才好回退)。
"""
import argparse
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_TOKEN")
API = "https://api.finmindtrade.com/api/v4/data"
STATE = "fundamental_backfill_state"

# 法定公告期限:{財季結束月日: (公告年偏移, 月, 日)}
DEADLINE = {(3, 31): (0, 5, 15), (6, 30): (0, 8, 14),
            (9, 30): (0, 11, 14), (12, 31): (1, 3, 31)}


def available_from(period_end: datetime):
    key = (period_end.month, period_end.day)
    if key not in DEADLINE:
        return None                       # 非標準財季,無法判定公告日 → 捨棄
    dy, m, d = DEADLINE[key]
    return datetime(period_end.year + dy, m, d)


def fetch(dataset, sid, start="2015-01-01", retries=3):
    for i in range(retries):
        try:
            r = requests.get(API, params={"dataset": dataset, "data_id": sid,
                                          "start_date": start, "token": TOKEN}, timeout=45)
        except requests.RequestException:
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 200:
            return r.json().get("data", [])
        if r.status_code in (402, 429):    # 配額/限流
            return None
        time.sleep(3 * (i + 1))
    return []


def pivot(rows):
    """[{date,type,value}] -> {date: {type: value}}"""
    out = {}
    for r in rows:
        d = r.get("date")
        if d and r.get("type") is not None:
            out.setdefault(d, {})[r["type"]] = r.get("value")
    return out


def compute(sid, inc_rows, bal_rows):
    inc, bal = pivot(inc_rows), pivot(bal_rows)
    dates = sorted(set(inc) & set(bal))
    docs = []
    for i, d in enumerate(dates):
        pe = datetime.strptime(d, "%Y-%m-%d")
        af = available_from(pe)
        if af is None:
            continue
        # TTM:近四季加總(不足四季則跳過,避免單季年化造成失真)
        window = dates[max(0, i - 3):i + 1]
        if len(window) < 4:
            continue
        # 稅後淨利的欄名有兩種:一般產業用 IncomeAfterTaxes(複數),部分金融/
        # 保險業用 IncomeAfterTax(單數)。原本只取複數,單數那批整條 TTM 算不出來
        # → net_income_ttm 為 null → roe 也是 null。2026-08-12 實測 2024Q2 有 24 檔
        # 屬此情況(全市場該期用單數者 28 檔)。兩者不會同時出現(實測 both=0)。
        ni = sum((inc[w].get("IncomeAfterTaxes")
                  or inc[w].get("IncomeAfterTax") or 0) for w in window)
        rev = sum((inc[w].get("Revenue") or 0) for w in window)

        b = bal[d]
        eq = b.get("Equity") or b.get("EquityAttributableToOwnersOfParent")
        ta = b.get("TotalAssets")
        li = b.get("Liabilities")
        if not eq or not ta:
            continue

        docs.append({
            "stock_id": sid,
            "period_end": pe,
            "available_from": af,
            "roe": ni / eq * 100,
            "roa": ni / ta * 100,
            "profit_margin": (ni / rev * 100) if rev else None,
            "debt_ratio": (li / ta * 100) if li is not None else None,
            "net_income_ttm": ni,
            "revenue_ttm": rev,
            "equity": eq,
            "total_assets": ta,
            "source": "computed:FinMind",
            "updated_at": datetime.now(),
        })
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-id", help="只跑單檔(驗證用)")
    ap.add_argument("--limit", type=int, default=99999)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.35)
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    if not TOKEN:
        raise SystemExit("FINMIND token 未設定")

    if args.stock_id:
        targets = [args.stock_id]
    else:
        from datetime import timedelta
        lat = db.stock_price.find_one(sort=[("date", -1)])["date"]
        targets = sorted(
            s for s in db.stock_price.distinct("stock_id",
                                               {"date": {"$gte": lat - timedelta(days=40)}})
            if len(s) == 4 and not s.startswith("00"))
        if args.resume:
            done = {r["stock_id"] for r in db[STATE].find({}, {"stock_id": 1})}
            targets = [s for s in targets if s not in done]
            print(f"續跑:已完成 {len(done)},剩 {len(targets)}")
        targets = targets[:args.limit]

    print(f"待處理 {len(targets)} 檔")
    tot_docs = 0
    for i, sid in enumerate(targets, 1):
        inc = fetch("TaiwanStockFinancialStatements", sid)
        if inc is None:
            print(f"⚠️ 配額耗盡,已處理 {i-1}/{len(targets)},可用 --resume 續跑")
            break
        time.sleep(args.sleep)
        bal = fetch("TaiwanStockBalanceSheet", sid)
        if bal is None:
            print(f"⚠️ 配額耗盡,已處理 {i-1}/{len(targets)},可用 --resume 續跑")
            break
        time.sleep(args.sleep)

        docs = compute(sid, inc or [], bal or [])
        if docs:
            db.fundamental_factors.bulk_write(
                [UpdateOne({"stock_id": d["stock_id"], "period_end": d["period_end"]},
                           {"$set": d}, upsert=True) for d in docs], ordered=False)
            tot_docs += len(docs)
        db[STATE].update_one({"stock_id": sid},
                             {"$set": {"periods": len(docs), "at": datetime.now()}},
                             upsert=True)

        if args.stock_id:
            print(f"\n{sid}: {len(docs)} 期")
            for d in docs[-5:]:
                print(f"   期末 {d['period_end']:%Y-%m-%d} → 可用起 {d['available_from']:%Y-%m-%d}"
                      f"  roe={d['roe']:6.2f}%  roa={d['roa']:5.2f}%"
                      f"  淨利率={d['profit_margin']:6.2f}%  負債比={d['debt_ratio']:5.2f}%")
        elif i % 50 == 0:
            print(f"  … {i}/{len(targets)}  累計 {tot_docs:,} 期")

    db.fundamental_factors.create_index([("stock_id", 1), ("period_end", 1)], unique=True)
    db.fundamental_factors.create_index([("stock_id", 1), ("available_from", 1)])
    print(f"\n完成:寫入 {tot_docs:,} 期 / 涵蓋 "
          f"{len(db.fundamental_factors.distinct('stock_id')):,} 檔")


if __name__ == "__main__":
    main()
