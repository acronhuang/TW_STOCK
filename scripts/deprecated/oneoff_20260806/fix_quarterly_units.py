#!/usr/bin/env python3
"""
一次性修正 quarterly_earnings 單位/累計 bug
==========================================
根因：TWSE/TPEX OpenAPI(t187ap14) 的營收/營業利益/稅後淨利為「千元 + 累計(YTD)」，
      但 FinMind 來源(2025Q3以前)為「元 + 單季」。twse_quarterly_sync 未轉換 →
      2025Q4、2026Q1 兩季金額小 ~1000 倍且 Q4 是全年累計 → revenue_yoy 全市場假衰退。

修正規則（只動 data_source ∈ TWSE_OpenAPI/TPEX_OpenAPI 的記錄）：
  - 季別1 : 累計=單季 → 金額 ×1000（EPS 不動，已是元）
  - 季別4 : 全年累計 → 單季 = (×1000 後全年) − 同年 Q1+Q2+Q3 單季(FinMind, 元)
            無法湊齊前三季者 → 金額設 None(不餵錯數)，保留 margins(比率正確)
  income['unit_fixed']=True 作為冪等防護(已修者跳過)。
用法： python scripts/fix_quarterly_units.py --dry-run    # 先看
       python scripts/fix_quarterly_units.py              # 套用
"""
from __future__ import annotations
import argparse
from pymongo import MongoClient

DB = MongoClient('mongodb://localhost:27017')['tw_stock_analysis']
COL = DB.quarterly_earnings
MONEY = ['revenue', 'operating_income', 'net_income']
BAD_SRC = {'TWSE_OpenAPI', 'TPEX_OpenAPI'}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def nine_month(symbol: str, year: int):
    """同年 Q1+Q2+Q3 單季合計(元)；回 (sums_dict, eps_sum, 齊全?)。"""
    sums = {k: 0.0 for k in MONEY}
    eps_sum = 0.0
    have = 0
    for s in (1, 2, 3):
        d = COL.find_one({'symbol': symbol, 'year': year, 'season': s})
        inc = d.get('income', {}) if d else {}
        if d and inc.get('revenue') is not None and d.get('data_source') not in BAD_SRC:
            have += 1
            for k in MONEY:
                sums[k] += _f(inc.get(k)) or 0
            eps_sum += _f(inc.get('eps')) or 0
    return sums, eps_sum, (have == 3)


def fix_one(doc: dict, dry: bool):
    inc = dict(doc.get('income', {}))
    if inc.get('unit_fixed'):
        return None  # 已修
    season = doc['season']
    year = doc['year']
    note = ''
    if season == 1:
        for k in MONEY:
            if _f(inc.get(k)) is not None:
                inc[k] = _f(inc[k]) * 1000
        note = '×1000(Q1單季)'
    elif season == 4:
        nine, eps9, ok = nine_month(doc['symbol'], year)
        if ok:
            for k in MONEY:
                fy = _f(inc.get(k))
                inc[k] = round(fy * 1000 - nine[k]) if fy is not None else None
            if _f(inc.get('eps')) is not None:
                inc['eps'] = round(_f(inc['eps']) - eps9, 2)
            note = '×1000−9M(Q4單季)'
        else:
            for k in MONEY:
                inc[k] = None      # 無法反推 → 不餵錯數
            note = '無前三季→金額設None'
    else:
        return None
    # 重算 margins（單季基準）
    rev, oi, ni = _f(inc.get('revenue')), _f(inc.get('operating_income')), _f(inc.get('net_income'))
    if rev and oi is not None:
        inc['operating_margin'] = round(oi / rev * 100, 2)
    if rev and ni is not None:
        inc['net_margin'] = round(ni / rev * 100, 2)
    inc['unit_fixed'] = True
    if not dry:
        COL.update_one({'_id': doc['_id']}, {'$set': {'income': inc}})
    return note, inc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--sample', default='2330')
    args = ap.parse_args()

    q = {'data_source': {'$in': list(BAD_SRC)},
         '$or': [{'year': 2025, 'season': 4}, {'year': 2026, 'season': 1}]}
    docs = list(COL.find(q))
    print(f"待修記錄：{len(docs)} 筆 (2025Q4 + 2026Q1, TWSE/TPEX)")

    # 先示範 sample
    print(f"\n=== 範例 {args.sample} ===")
    for d in COL.find({'symbol': args.sample, 'data_source': {'$in': list(BAD_SRC)}}):
        before = d.get('income', {})
        r = fix_one(d, dry=True)
        if r:
            note, after = r
            print(f"  {d['year']}Q{d['season']} [{note}]")
            print(f"    營收  {before.get('revenue')} → {after.get('revenue')}")
            print(f"    淨利  {before.get('net_income')} → {after.get('net_income')}")
            print(f"    EPS   {before.get('eps')} → {after.get('eps')}")

    if args.dry_run:
        print("\n[DRY RUN] 未寫入。")
        return

    stats = {'fixed': 0, 'skip': 0, 'null': 0}
    for d in docs:
        r = fix_one(d, dry=False)
        if r is None:
            stats['skip'] += 1
        else:
            stats['fixed'] += 1
            if 'None' in r[0]:
                stats['null'] += 1
    print(f"\n完成：修正 {stats['fixed']} 筆（其中 {stats['null']} 筆無前三季設None）、跳過 {stats['skip']} 筆")


if __name__ == '__main__':
    main()
