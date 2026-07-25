#!/usr/bin/env python3
"""Winsorize garbage outliers in fundamental_factors (tiny-denominator artifacts).

Clips to sane financial bounds; original preserved in <field>_raw (reversible):
  roe / roa / profit_margin -> [-100, 100]   debt_ratio -> [0, 100]

IMPORTANT: iterates via a FULL scan and filters in Python. Field-predicate queries
(e.g. {roe:{$gt:100}}) under-count on this collection via pymongo, so they are NOT
used. The strategy's _fundamental_quality filters by available_from, not these
fields, so it is unaffected either way.

Usage: python winsorize_fundamental.py --dry-run   |   python winsorize_fundamental.py
"""
import argparse
from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

BOUNDS = {"roe": (-100.0, 100.0), "roa": (-100.0, 100.0),
          "profit_margin": (-100.0, 100.0), "debt_ratio": (0.0, 100.0)}

def num(v):
    if v is None: return None
    if isinstance(v, Decimal128): return float(v.to_decimal())
    if isinstance(v, (int, float)): return float(v)
    try: return float(v)
    except Exception: return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=2000)
    a = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    col = db.fundamental_factors

    proj = {f: 1 for f in BOUNDS}
    proj.update({f + "_raw": 1 for f in BOUNDS})
    per_field = {f: 0 for f in BOUNDS}
    docs_touched = 0
    samples = []
    ops = []
    for d in col.find({}, proj):
        setd = {}
        for f, (lo, hi) in BOUNDS.items():
            v = num(d.get(f))
            if v is None:
                continue
            if v < lo or v > hi:
                clipped = lo if v < lo else hi
                setd[f] = clipped
                if (f + "_raw") not in d:          # preserve the true original once
                    setd[f + "_raw"] = v
                per_field[f] += 1
        if setd:
            docs_touched += 1
            if len(samples) < 8:
                samples.append((d.get("stock_id"), {k: round(vv, 1) for k, vv in setd.items()
                                                    if not k.endswith("_raw")}))
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": setd}))
            if len(ops) >= a.batch and not a.dry_run:
                col.bulk_write(ops, ordered=False); ops = []
    if ops and not a.dry_run:
        col.bulk_write(ops, ordered=False)

    print("per-field clips:", per_field)
    print("docs_touched:", docs_touched, "dry_run:", a.dry_run)
    for s in samples:
        print("  sample", s)

if __name__ == "__main__":
    main()
