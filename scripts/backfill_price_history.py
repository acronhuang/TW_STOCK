#!/usr/bin/env python3
"""
回補被截斷的個股歷史股價
========================
問題：~177 檔上市櫃股(如長榮2603、中信金2891)的 stock_price 只到 2026-02-11，
      pre-2026 歷史價缺失 → beta/風險/動能等需長序列的計算樣本太短。
原因：歷史回補當時漏掉這批，只有每日更新從 2026-02 起累積。

修法：對「最早日期晚於門檻(預設2025-07-01)」的 4 位數股票，用 FinMind TaiwanStockPrice
      (免費版可取~2022起) 回補缺失區間，寫入 stock_price(Decimal128, 對齊既有schema)。
      唯一索引(symbol,date) 防重複；真新股 FinMind 只回其上市後資料、無害。

用法： python scripts/backfill_price_history.py --dry-run          # 看名單
       python scripts/backfill_price_history.py --limit 3         # 先測3檔
       python scripts/backfill_price_history.py                   # 全跑
"""
from __future__ import annotations
import os
import re
import sys
import time
import argparse
import datetime
from pathlib import Path

import requests
from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

DB = MongoClient('mongodb://localhost:27017')['tw_stock_analysis']
FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'
TOKEN = os.getenv('FINMIND_API_TOKEN', '')
START = '2022-01-01'


def _d128(v):
    try:
        return Decimal128(str(float(v)))
    except (TypeError, ValueError):
        return None


def targets(cutoff_date: datetime.datetime):
    """回傳需回補的股票 [(symbol, name, current_earliest)]。"""
    rows = DB.stock_price.aggregate(
        [{'$group': {'_id': '$symbol', 'first': {'$min': '$date'}, 'cnt': {'$sum': 1}}}],
        allowDiskUse=True)
    out = []
    for r in rows:
        sym = str(r['_id'])
        if not re.fullmatch(r'\d{4}', sym):
            continue
        first = r['first']
        if not isinstance(first, datetime.datetime):
            continue
        if first >= cutoff_date:                     # 最早日期偏晚 = 被截斷/新股
            nm = DB.stock_price.find_one({'symbol': sym}, sort=[('date', -1)]) or {}
            out.append((sym, nm.get('name', ''), first))
    return sorted(out, key=lambda x: x[0])


def fetch_finmind(symbol: str):
    try:
        r = requests.get(FINMIND_URL, params={
            'dataset': 'TaiwanStockPrice', 'data_id': symbol,
            'start_date': START, 'token': TOKEN}, timeout=30)
        if r.status_code == 402:
            return None  # 配額耗盡
        if r.status_code != 200:
            return []
        return r.json().get('data', [])
    except Exception:
        return []


def backfill_one(symbol: str, name: str, earliest: datetime.datetime, dry: bool):
    data = fetch_finmind(symbol)
    if data is None:
        return 'quota'
    if not data:
        return 0
    ops = []
    now = datetime.datetime.now()
    for row in data:
        try:
            dt = datetime.datetime.strptime(row['date'], '%Y-%m-%d')
        except (KeyError, ValueError):
            continue
        if dt >= earliest:        # 只補缺失的早期區間（既有的不動）
            continue
        close = _d128(row.get('close'))
        doc = {
            'symbol': symbol, 'stock_id': symbol, 'date': dt, 'name': name,
            'open': _d128(row.get('open')), 'high': _d128(row.get('max')),
            'low': _d128(row.get('min')), 'close': close, 'adj_close': close,
            'volume': _d128(row.get('Trading_Volume')),
            'data_source': 'FinMind_backfill', 'updated_at': now,
        }
        ops.append(UpdateOne({'symbol': symbol, 'date': dt}, {'$setOnInsert': doc}, upsert=True))
    if not ops:
        return 0
    if dry:
        return len(ops)
    res = DB.stock_price.bulk_write(ops, ordered=False)
    return res.upserted_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0, help='只處理前N檔(測試)')
    ap.add_argument('--cutoff', default='2025-07-01', help='最早日期晚於此即回補')
    ap.add_argument('--sleep', type=float, default=0.3)
    args = ap.parse_args()

    cutoff = datetime.datetime.strptime(args.cutoff, '%Y-%m-%d')
    tgts = targets(cutoff)
    if args.limit:
        tgts = tgts[:args.limit]
    print(f"待回補股票：{len(tgts)} 檔（最早日期晚於 {args.cutoff}）")
    if args.dry_run and not args.limit:
        for s, n, f in tgts[:20]:
            print(f"  {s} {n} 目前最早={f.date()}")
        print("  ... (--dry-run，未抓取)")
        return

    total = 0
    for i, (sym, name, first) in enumerate(tgts, 1):
        n = backfill_one(sym, name, first, args.dry_run)
        if n == 'quota':
            print(f"  ⚠️ FinMind 配額耗盡，停在第 {i} 檔（{sym}）")
            break
        total += n if isinstance(n, int) else 0
        if i <= 10 or i % 25 == 0:
            print(f"  [{i}/{len(tgts)}] {sym} {name}: {'(dry)' if args.dry_run else '補'}{n} 筆")
        time.sleep(args.sleep)
    print(f"\n完成：{'(DRY) 預計' if args.dry_run else '實際'}回補 {total} 筆")


if __name__ == '__main__':
    main()
