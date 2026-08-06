#!/usr/bin/env python3
"""A2:從回填的 quarterly_earnings 算基本面因子(含真 FCF/ROIC),帶 PIT 公告落後。

改讀本地 `quarterly_earnings`(已回填 2016~,含 income/balance/cashflow),
不再直接打 FinMind(省配額、用 10 年資料)。

⚠️ 兩個資料形態陷阱(2026-07-25 實測確認):
  - income(revenue/operating_income/net_income)= **單季**值 → TTM 取近四季加總。
  - cashflow(OCF/capex/fcf)= **YTD 累計** → 須先差分成單季(Q_n - Q_{n-1};Q1 as-is)再 TTM。
  - income 無 gross_profit → 毛利率用不了,護城河用 operating_margin。

PIT available_from = 法定公告期限(保守):Q1→5/15 Q2→8/14 Q3→11/14 Q4→次年3/31。

寫 `fundamental_factors`(upsert by stock_id+period_end),不動 stock_factors(套用是下一步)。
用法: build_fundamental_factors_v2.py [--stock-id 2330] [--limit N] [--min-quarters 8]
"""
import argparse
from datetime import datetime

from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

DEADLINE = {(3, 31): (0, 5, 15), (6, 30): (0, 8, 14),
            (9, 30): (0, 11, 14), (12, 31): (1, 3, 31)}
SEASON_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
TAX = 0.20   # NOPAT 近似稅率


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


def available_from(year, season):
    key = SEASON_END.get(season)
    if not key:
        return None, None
    pe = datetime(year, key[0], key[1])
    dy, m, d = DEADLINE[key]
    return pe, datetime(year + dy, m, d)


def compute(qs):
    """qs: quarterly_earnings docs(已按 year,season 升冪)。回傳 factor docs。"""
    # 先把每季拆出需要的原始值
    rows = []
    for q in qs:
        inc = q.get("income") or {}
        bal = q.get("balance") or {}
        cf = q.get("cashflow") or {}
        rows.append({
            "year": q["year"], "season": q["season"],
            "revenue": _f(inc.get("revenue")),
            "op_income": _f(inc.get("operating_income")),
            "net_income": _f(inc.get("net_income")),
            "op_margin": _f(inc.get("operating_margin")),
            # cashflow 是 YTD
            "ocf_ytd": _f(cf.get("operating_cash_flow")),
            "capex_ytd": _f(cf.get("capex")),
            "fcf_ytd": _f(cf.get("fcf")),
            # balance 是時點
            "total_assets": _f(bal.get("total_assets")),
            "current_liab": _f(bal.get("current_liabilities")),
            "equity": _f(bal.get("equity_parent")) or _f(bal.get("total_equity")),
            "total_liab": _f(bal.get("total_liabilities")),
        })

    # cashflow YTD → 單季(需同年前一季;Q1 直接用 YTD)
    by_ys = {(r["year"], r["season"]): r for r in rows}
    for r in rows:
        for k in ("ocf", "capex", "fcf"):
            ytd = r[k + "_ytd"]
            if ytd is None:
                r[k + "_q"] = None
                continue
            if r["season"] == 1:
                r[k + "_q"] = ytd
            else:
                prev = by_ys.get((r["year"], r["season"] - 1))
                pv = prev[k + "_ytd"] if prev else None
                r[k + "_q"] = (ytd - pv) if pv is not None else None

    docs = []
    for i, r in enumerate(rows):
        pe, af = available_from(r["year"], r["season"])
        if af is None:
            continue
        window = rows[max(0, i - 3):i + 1]
        if len(window) < 4:
            continue

        def ttm(key):
            vals = [w.get(key) for w in window]
            return sum(vals) if all(v is not None for v in vals) else None

        ni_ttm = ttm("net_income")
        rev_ttm = ttm("revenue")
        op_ttm = ttm("op_income")
        fcf_ttm = ttm("fcf_q")
        ocf_ttm = ttm("ocf_q")

        ta, cl, eq, li = r["total_assets"], r["current_liab"], r["equity"], r["total_liab"]
        invested = (ta - cl) if (ta and cl) else None

        doc = {
            "stock_id": qs[0]["symbol"], "period_end": pe, "available_from": af,
            "year": r["year"], "season": r["season"],
            "roe": (ni_ttm / eq * 100) if (ni_ttm is not None and eq) else None,
            "roa": (ni_ttm / ta * 100) if (ni_ttm is not None and ta) else None,
            "roic": (op_ttm * (1 - TAX) / invested * 100) if (op_ttm is not None and invested and invested > 0) else None,
            "profit_margin": (ni_ttm / rev_ttm * 100) if (ni_ttm is not None and rev_ttm) else None,
            "op_margin": r["op_margin"],
            "fcf_margin": (fcf_ttm / rev_ttm * 100) if (fcf_ttm is not None and rev_ttm) else None,
            "debt_ratio": (li / ta * 100) if (li is not None and ta) else None,
            "net_income_ttm": ni_ttm, "revenue_ttm": rev_ttm,
            "fcf_ttm": fcf_ttm, "ocf_ttm": ocf_ttm,
            "equity": eq, "total_assets": ta,
            "source": "computed:quarterly_earnings", "updated_at": datetime.now(),
        }
        docs.append(doc)
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-id")
    ap.add_argument("--limit", type=int, default=99999)
    ap.add_argument("--min-quarters", type=int, default=4)
    ap.add_argument("--apply", action="store_true", help="寫入(預設 dry-run 只印統計)")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    if args.stock_id:
        syms = [args.stock_id]
    else:
        syms = sorted(s for s in db.quarterly_earnings.distinct("symbol")
                      if len(s) == 4 and not s.startswith("00"))[:args.limit]

    print(f"待處理 {len(syms)} 檔 | {'APPLY' if args.apply else 'DRY-RUN'}")
    tot = 0
    for j, sid in enumerate(syms, 1):
        qs = list(db.quarterly_earnings.find(
            {"symbol": sid}).sort([("year", 1), ("season", 1)]))
        if len(qs) < args.min_quarters:
            continue
        docs = compute(qs)
        tot += len(docs)
        if args.stock_id:
            print(f"{sid}: {len(qs)} 季 → {len(docs)} 因子期")
            for d in docs[-6:]:
                print(f"  {d['period_end']:%Y-%m-%d}(可用{d['available_from']:%m/%d}) "
                      f"roe={_p(d['roe'])} roic={_p(d['roic'])} fcf率={_p(d['fcf_margin'])} "
                      f"淨利率={_p(d['profit_margin'])} 負債={_p(d['debt_ratio'])} "
                      f"FCF_TTM={_m(d['fcf_ttm'])}")
        if args.apply and docs:
            db.fundamental_factors.bulk_write(
                [UpdateOne({"stock_id": d["stock_id"], "period_end": d["period_end"]},
                           {"$set": d}, upsert=True) for d in docs], ordered=False)
        if not args.stock_id and j % 100 == 0:
            print(f"  … {j}/{len(syms)} 累計 {tot:,} 期")
    if args.apply:
        db.fundamental_factors.create_index([("stock_id", 1), ("period_end", 1)], unique=True)
        db.fundamental_factors.create_index([("stock_id", 1), ("available_from", 1)])
    print(f"\n{'寫入' if args.apply else '試算'} {tot:,} 期")


def _p(v):
    return f"{v:6.2f}%" if v is not None else "  n/a "


def _m(v):
    return f"{v/1e8:,.0f}億" if v is not None else "n/a"


if __name__ == "__main__":
    main()
