#!/usr/bin/env python3
"""
回補 quarterly_earnings 的 gross_margin（毛利率）
================================================
背景：TWSE/TPEX t187ap14 無「營業毛利」欄 → quarterly_earnings 從沒存過 gross_margin
      → financial_health 的 avg_field(recent4,'gross_margin') 永遠 None。
      但 financial_statements(FinMind, 192檔) 的 income_statement 有 GrossProfit + Revenue。

修法：逐 (symbol, year, season) 從 financial_statements 算 gross_margin = GrossProfit/Revenue×100，
      寫進 quarterly_earnings.income.gross_margin。毛利率為比率、單位無關。
用法： python scripts/backfill_gross_margin.py [--dry-run]
"""
from __future__ import annotations
import argparse
from pymongo import MongoClient

DB = MongoClient('mongodb://localhost:27017')['tw_stock_analysis']


def income_value(income_statement, type_name):
    if isinstance(income_statement, list):
        for row in income_statement:
            if row.get('type') == type_name:
                try:
                    return float(row.get('value'))
                except (TypeError, ValueError):
                    return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    updated = skipped = no_data = 0
    sample = []
    for fs in DB.financial_statements.find({}, {'symbol': 1, 'year': 1, 'season': 1, 'data': 1}):
        sym, yr, sea = fs.get('symbol'), fs.get('year'), fs.get('season')
        if not (sym and yr and sea):
            continue
        inc_st = (fs.get('data') or {}).get('income_statement')
        rev = income_value(inc_st, 'Revenue')
        gp = income_value(inc_st, 'GrossProfit')
        if not rev or gp is None or rev == 0:
            no_data += 1
            continue
        gm = round(gp / rev * 100, 2)
        qe = DB.quarterly_earnings.find_one({'symbol': sym, 'year': yr, 'season': sea})
        if not qe:
            skipped += 1
            continue
        if not args.dry_run:
            DB.quarterly_earnings.update_one(
                {'_id': qe['_id']}, {'$set': {'income.gross_margin': gm}})
        updated += 1
        if len(sample) < 6:
            sample.append(f"{sym} {yr}Q{sea} gross_margin={gm}%")

    print(f"{'[DRY] ' if args.dry_run else ''}回補 gross_margin：更新 {updated}、"
          f"無對應quarterly {skipped}、無毛利資料 {no_data}")
    for s in sample:
        print("  " + s)


if __name__ == '__main__':
    main()
