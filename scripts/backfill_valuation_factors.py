#!/usr/bin/env python3
"""估值因子回填 (Phase 價值升級·維4)

用 ValuationAnalyzer(DCF+DDM+PE Band 綜合) 對全市場算「合理價 fair_value」,
再對現價算「安全邊際 margin_of_safety% = (合理價-現價)/現價」,寫進 stock_factors 最新日。
安全邊際>0=低估(便宜且有內在價值),供 value 因子/dailypicks/問答用,勝過只看 PE/PB。

台股缺完整現金流量表 → valuation_models 的 FCF 是「淨利×係數」粗估(其註解已說明),此為已知限制。

用法: python scripts/backfill_valuation_factors.py [--dry-run] [--limit N] [--symbols 2330 5515]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

from src.analysis.valuation_models import ValuationAnalyzer

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
VM = ValuationAnalyzer("mongodb://localhost:27017/")


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


def latest_price(sym):
    p = DB.stock_price.find_one({"symbol": sym}, sort=[("date", -1)], projection={"close": 1})
    return _f((p or {}).get("close"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--symbols", nargs="+")
    ap.add_argument("--batch", type=int, default=500)
    a = ap.parse_args()

    ld = DB.stock_factors.find_one(sort=[("date", -1)], projection={"date": 1})["date"]
    if a.symbols:
        syms = a.symbols
    else:
        syms = sorted(DB.stock_factors.distinct("symbol", {"date": ld}))
        if a.limit:
            syms = syms[:a.limit]
    print(f"最新因子日 {ld} | 目標 {len(syms)} 檔")

    ops = []
    n_ok = n_fv = 0
    samples = []
    for sym in syms:
        try:
            r = VM.analyze(sym)
        except Exception:
            continue
        fv = (r.get("composite") or {}).get("fair_value")
        px = latest_price(sym)
        setd, unsetd = {}, {}
        if fv and fv > 0:
            setd["fair_value"] = round(float(fv), 2)
            n_fv += 1
            if px and px > 0:
                mos = round((fv - px) / px * 100, 2)
                setd["margin_of_safety"] = mos
        else:
            unsetd["fair_value"] = ""
            unsetd["margin_of_safety"] = ""
        upd = {}
        if setd:
            upd["$set"] = setd
        if unsetd:
            upd["$unset"] = unsetd
        if upd:
            ops.append(UpdateOne({"symbol": sym, "date": ld}, upd))
            n_ok += 1
            if a.symbols and len(samples) < 10:
                samples.append((sym, setd.get("fair_value"), px, setd.get("margin_of_safety")))
        if len(ops) >= a.batch and not a.dry_run:
            DB.stock_factors.bulk_write(ops, ordered=False)
            ops = []
    if ops and not a.dry_run:
        DB.stock_factors.bulk_write(ops, ordered=False)

    for s in samples:
        print(f"  {s[0]}: 合理價{s[1]} 現價{s[2]} 安全邊際{s[3]}%")
    print(f"處理 {n_ok} 檔, 其中有合理價 {n_fv} 檔, dry_run={a.dry_run}")


if __name__ == "__main__":
    main()
