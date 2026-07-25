#!/usr/bin/env python3
"""歷史 margin_of_safety 回填 (維4 回測用·point-in-time)

用 PIT 子類覆寫 valuation_models 的取數 helper（只用「as_of 日前已公布」的財報/股利/股價）,
以 DCF+DDM 綜合算 fair_value(丟 pe_band：其 cutoff 硬寫 now 會前視,且與 pe_ratio 因子重疊)。
fair_value 隨年報年更一次 → 每個回測日 margin_of_safety% = fair_value(最近as_of≤date)/當日close - 1。
寫進 stock_factors 歷史各日,供 value 因子回測(避免前視)。

用法: python scripts/hist_valuation_backfill.py [--dry-run] [--symbols 2330 5515] [--limit N]
"""
import argparse
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

from src.analysis.valuation_models import ValuationAnalyzer, _to_float

# 年報法定公告截止 3/31；季報 5/15,8/14,11/14。fair_value 由年度資料驅動,故以年報點為 as_of。
def publish_date(year, season):
    if season == 1:
        return dt.datetime(year, 5, 15)
    if season == 2:
        return dt.datetime(year, 8, 14)
    if season == 3:
        return dt.datetime(year, 11, 14)
    if season == 4:
        return dt.datetime(year + 1, 3, 31)
    return None


class PITValuation(ValuationAnalyzer):
    """point-in-time：只看 as_of 日前已公布的財報/股利/股價。"""
    def __init__(self, uri, as_of):
        super().__init__(uri)
        self.as_of = as_of

    def _get_quarterly_earnings(self, symbol, years=5):
        min_year = self.as_of.year - years
        rows = list(self.db.quarterly_earnings.find(
            {"symbol": symbol, "year": {"$gte": min_year}},
            {"year": 1, "season": 1, "income": 1, "balance": 1}
        ).sort([("year", 1), ("season", 1)]))
        out = []
        for r in rows:
            pd_ = publish_date(int(r["year"]), int(r["season"]))
            if pd_ and pd_ <= self.as_of:
                out.append(r)
        return out

    def _get_dividend_history(self, symbol):
        rows = list(self.db.dividend_detail.find(
            {"stock_id": symbol},
            {"date": 1, "cash_earnings_distribution": 1, "stock_earnings_distribution": 1}
        ).sort("date", -1))
        cut = self.as_of.strftime("%Y-%m-%d")   # dividend_detail.date 是字串,用 ISO 字串比
        return [r for r in rows if r.get("date") and str(r["date"])[:10] <= cut]

    def _get_current_price(self, symbol):
        rec = self.db.stock_price.find_one(
            {"symbol": symbol, "date": {"$lte": self.as_of}}, {"close": 1}, sort=[("date", -1)])
        return _to_float(rec["close"]) if rec else None

    def fair_value_dcf_ddm(self, symbol):
        price = self._get_current_price(symbol)
        if not price:
            return None
        fvs, ws = [], []
        for fn, w in ((self.dcf_valuation, 0.4), (self.ddm_valuation, 0.3)):
            try:
                res = fn(symbol, price)
            except Exception:
                res = None
            if res and res.get("fair_value") and res["fair_value"] > 0:
                fvs.append(res["fair_value"]); ws.append(w)
        if not fvs:
            return None
        return sum(f * w for f, w in zip(fvs, ws)) / sum(ws)


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


URI = "mongodb://localhost:27017/"
DB = MongoClient(URI)["tw_stock_analysis"]
# 財報起 2022 → 首個完整年(2022)於 2023-03-31 可用。as_of 年報點:
AS_OFS = [dt.datetime(2023, 3, 31), dt.datetime(2024, 3, 31),
          dt.datetime(2025, 3, 31), dt.datetime(2026, 3, 31)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--symbols", nargs="+")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=5000)
    a = ap.parse_args()

    if a.symbols:
        syms = a.symbols
    else:
        syms = sorted(DB.quarterly_earnings.distinct("symbol"))
        if a.limit:
            syms = syms[:a.limit]
    print(f"符合(有財報)股票 {len(syms)} 檔 | as_of 點: {[d.strftime('%Y-%m-%d') for d in AS_OFS]}")

    # 1) 每檔在各 as_of 點算 fair_value
    vms = {ao: PITValuation(URI, ao) for ao in AS_OFS}
    fv_hist = {}   # sym -> [(as_of, fv), ...] 升冪
    n_fv = 0
    for i, sym in enumerate(syms, 1):
        hist = []
        for ao in AS_OFS:
            try:
                fv = vms[ao].fair_value_dcf_ddm(sym)
            except Exception:
                fv = None
            if fv and fv > 0:
                hist.append((ao, fv))
        if hist:
            fv_hist[sym] = hist
            n_fv += 1
        if a.symbols:
            print(f"  {sym}: " + " | ".join(f"{ao:%Y-%m}→合理價{fv:.1f}" for ao, fv in hist) if hist else f"  {sym}: 無")
        if i % 300 == 0:
            print(f"    ...{i}/{len(syms)} 已算 fair_value")
    print(f"有 fair_value 的股票: {n_fv}")

    # 2) 對 stock_factors 各日填 margin_of_safety = fv(最近as_of≤date)/close - 1
    ops = []
    n_docs = 0
    for sym, hist in fv_hist.items():
        for d in DB.stock_factors.find({"symbol": sym, "date": {"$gte": AS_OFS[0]}},
                                       {"date": 1, "close": 1}):
            dd = d["date"]
            fv = None
            for ao, v in hist:                 # 取最近的 as_of ≤ dd
                if ao <= dd:
                    fv = v
                else:
                    break
            if fv is None:
                continue
            close = _f(d.get("close"))
            if not close:                       # stock_factors 可能無 close → 查 price
                p = DB.stock_price.find_one({"symbol": sym, "date": dd}, {"close": 1})
                close = _f((p or {}).get("close"))
            if not close or close <= 0:
                continue
            mos = round((fv - close) / close * 100, 2)
            ops.append(UpdateOne({"symbol": sym, "date": dd},
                                 {"$set": {"fair_value_pit": round(fv, 2), "margin_of_safety_pit": mos}}))
            n_docs += 1
            if len(ops) >= a.batch and not a.dry_run:
                DB.stock_factors.bulk_write(ops, ordered=False); ops = []
    if ops and not a.dry_run:
        DB.stock_factors.bulk_write(ops, ordered=False)
    print(f"回填 margin_of_safety_pit: {n_docs} 筆(docs), dry_run={a.dry_run}")


if __name__ == "__main__":
    main()
