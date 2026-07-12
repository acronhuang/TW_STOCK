#!/usr/bin/env python3
"""
FinMind API 五年季報批次下載（支援 Token）
=====================================
透過 FinMind API 下載損益表＋資產負債表，存入 quarterly_earnings。
無 Token 免費使用；提供 Token 可提高速率上限（600次/小時）。

Usage:
    python finmind_quarterly_backfill.py --token <JWT>          # 有 Token（6s 間隔）
    python finmind_quarterly_backfill.py                        # 無 Token（2s 間隔）
    python finmind_quarterly_backfill.py --resume --token <JWT> # 跳過已有資料續跑
    python finmind_quarterly_backfill.py --years 3 --token <JWT># 只下最近 3 年
"""

from __future__ import annotations

import argparse
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import urllib3
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

MONGO_URI  = 'mongodb://localhost:27017/'
DB_NAME    = 'tw_stock_analysis'
COLL_NAME  = 'quarterly_earnings'
FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'
HEADERS    = {'User-Agent': 'Mozilla/5.0 (compatible; TW-Stock-Analyzer/1.0)'}

# FinMind type → 我們的欄位對照（損益表）
INCOME_MAP = {
    'Revenue':          'revenue',
    'OperatingIncome':  'operating_income',
    'IncomeAfterTaxes': 'net_income',
    'EPS':              'eps',
}

# 資產負債表重要科目（欄位名稱依 FinMind TaiwanStockBalanceSheet 實際回傳）
BALANCE_MAP = {
    'TotalAssets':                        'total_assets',
    'Liabilities':                        'total_liabilities',
    'Equity':                             'total_equity',
    'EquityAttributableToOwnersOfParent': 'equity_parent',
    'CashAndCashEquivalents':             'cash',
    'CurrentAssets':                      'current_assets',
    'CurrentLiabilities':                 'current_liabilities',
    'LongtermBorrowings':                 'long_term_debt',
    'AccountsReceivableNet':              'accounts_receivable',
    'Inventories':                        'inventory',
    'RetainedEarnings':                   'retained_earnings',
    'PropertyPlantAndEquipment':          'ppe',
}


def date_to_season(date_str: str) -> Optional[tuple[int, int]]:
    """
    '2024-03-31' → (2024, 1)
    '2024-06-30' → (2024, 2)
    '2024-09-30' → (2024, 3)
    '2024-12-31' → (2024, 4)
    """
    try:
        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
        m = dt.month
        if m == 3:
            season = 1
        elif m == 6:
            season = 2
        elif m == 9:
            season = 3
        elif m == 12:
            season = 4
        else:
            return None
        return dt.year, season
    except ValueError:
        return None


def _finmind_get(session: requests.Session, dataset: str, symbol: str,
                 start_date: str, end_date: str, token: str = '') -> list[dict]:
    """通用 FinMind API 請求，返回 data list。"""
    params = {
        'dataset':    dataset,
        'data_id':    symbol,
        'start_date': start_date,
        'end_date':   end_date,
    }
    if token:
        params['token'] = token
    try:
        r = session.get(FINMIND_URL, params=params, timeout=20)
        r.raise_for_status()
        raw = r.json()
        if raw.get('status') != 200:
            return []
        return raw.get('data', [])
    except Exception as exc:
        logger.warning(f"  {symbol} [{dataset}] 下載失敗: {exc}")
        return []


def _pivot_by_date(rows: list[dict], type_map: dict) -> dict[str, dict]:
    """將長格式資料 pivot 成 {date: {field: value}} 字典。"""
    by_date: dict[str, dict] = {}
    for row in rows:
        t = row.get('type', '')
        if t not in type_map:
            continue
        d = row.get('date', '')
        if d not in by_date:
            by_date[d] = {}
        by_date[d][type_map[t]] = row.get('value')
    return by_date


def fetch_quarterly(symbol: str, start_date: str, end_date: str,
                    session: requests.Session, token: str = '',
                    with_balance: bool = True) -> list[dict]:
    """
    下載單支股票損益表（＋資產負債表），返回標準化 list[dict]。
    """
    src = 'FinMind_Paid' if token else 'FinMind_Free'

    # 損益表
    income_rows   = _finmind_get(session, 'TaiwanStockFinancialStatements',
                                 symbol, start_date, end_date, token)
    income_by_dt  = _pivot_by_date(income_rows, INCOME_MAP)

    # 資產負債表（有 Token 才抓，節省免費額度）
    balance_by_dt: dict[str, dict] = {}
    if with_balance:
        bal_rows      = _finmind_get(session, 'TaiwanStockBalanceSheet',
                                     symbol, start_date, end_date, token)
        balance_by_dt = _pivot_by_date(bal_rows, BALANCE_MAP)

    # 合併所有出現的日期
    all_dates = set(income_by_dt) | set(balance_by_dt)
    records   = []
    for date_str in all_dates:
        ys = date_to_season(date_str)
        if ys is None:
            continue
        year, season = ys

        inc = income_by_dt.get(date_str, {})
        rev     = inc.get('revenue')
        op_inc  = inc.get('operating_income')
        net_inc = inc.get('net_income')
        eps     = inc.get('eps')

        income = {
            'revenue':          rev,
            'operating_income': op_inc,
            'net_income':       net_inc,
            'eps':              eps,
            'operating_margin': round(op_inc / rev * 100, 2) if rev and op_inc and rev != 0 else None,
            'net_margin':       round(net_inc / rev * 100, 2) if rev and net_inc and rev != 0 else None,
        }

        bal = balance_by_dt.get(date_str, {})
        eq  = bal.get('total_equity')
        # ROE = 淨利 / 股東權益
        if net_inc and eq and eq != 0:
            bal['roe'] = round(net_inc / eq * 100, 2)

        records.append({
            'symbol':      symbol,
            'year':        year,
            'season':      season,
            'income':      income,
            'balance':     bal,
            'cashflow':    {},
            'report_type': '合併',
            'data_source': src,
            'updated_at':  datetime.now(timezone.utc).replace(tzinfo=None),
        })

    return records


def upsert_records(records: list[dict], coll) -> tuple[int, int]:
    if not records:
        return 0, 0
    ops = [
        UpdateOne(
            {'symbol': r['symbol'], 'year': r['year'], 'season': r['season']},
            {
                '$setOnInsert': {
                    'cashflow':    {},
                    'report_type': '合併',
                },
                '$set': {
                    'income':      r['income'],
                    'balance':     r.get('balance', {}),
                    'data_source': r['data_source'],
                    'updated_at':  r['updated_at'],
                },
            },
            upsert=True,
        )
        for r in records
    ]
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


def main():
    parser = argparse.ArgumentParser(description='FinMind API 五年季報批次下載')
    parser.add_argument('--token',   type=str, default='',
                        help='FinMind API Token（有 Token 600次/小時，預設免費版）')
    parser.add_argument('--years',   type=int, default=5,
                        help='下載最近幾年（預設 5）')
    parser.add_argument('--delay',   type=float, default=None,
                        help='每支股票間隔秒數（有 Token 預設 6.0，無 Token 預設 2.0）')
    parser.add_argument('--resume',  action='store_true',
                        help='略過 quarterly_earnings 已有任何資料的股票')
    parser.add_argument('--no-balance', action='store_true',
                        help='略過資產負債表（只下載損益表，節省 API 次數）')
    parser.add_argument('--symbols', nargs='+', default=None,
                        help='只下載指定股票（空白分隔）')
    parser.add_argument('--limit',   type=int, default=None,
                        help='最多下載幾支（測試用）')
    args = parser.parse_args()

    # 有 Token 時每支股票查 2 個 dataset（損益+資產負債），每次請求消耗 1 次額度
    # 600次/小時 ÷ 2 dataset = 300 股/小時 → 每股 12 秒
    # 若只查損益表 (--no-balance)：600股/小時 → 每股 6 秒
    if args.delay is None:
        if args.token:
            args.delay = 12.0 if not args.no_balance else 6.0
        else:
            args.delay = 2.0

    # 日期範圍
    end_year   = datetime.now().year
    start_year = end_year - args.years + 1
    start_date = f'{start_year}-01-01'
    end_date   = f'{end_year}-12-31'

    # 連接 DB
    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]
    coll   = db[COLL_NAME]
    coll.create_index(
        [('symbol', 1), ('year', 1), ('season', 1)],
        unique=True, background=True,
    )

    # 取得股票清單（只含一般股票，排除 ETF/權證/0開頭）
    if args.symbols:
        symbols = sorted(args.symbols)
    else:
        all_syms = db.stock_price.distinct('symbol')
        symbols  = sorted(
            s for s in all_syms
            if s.isdigit() and len(s) == 4 and not s.startswith('0')
        )
        logger.info(f"全部代碼 {len(all_syms)} 支 → 一般股票 {len(symbols)} 支（排除 ETF/權證）")

    if args.resume:
        already = set(coll.distinct('symbol'))
        before  = len(symbols)
        symbols = [s for s in symbols if s not in already]
        logger.info(f"--resume: 跳過 {before - len(symbols)} 支已有資料的股票")

    if args.limit:
        symbols = symbols[:args.limit]

    total = len(symbols)
    mode  = f"Token({'有' if args.token else '無'}) | Balance({'跳過' if args.no_balance else '下載'})"
    logger.info(f"準備下載 {total} 支股票 | {start_date} ~ {end_date} | {mode} | 間隔 {args.delay}s")
    logger.info(f"預估時間: {total * args.delay / 60:.0f} 分鐘")

    session = requests.Session()
    session.headers.update(HEADERS)

    total_ins = total_mod = total_skip = 0
    for i, symbol in enumerate(symbols, 1):
        records = fetch_quarterly(symbol, start_date, end_date, session,
                                  token=args.token,
                                  with_balance=not args.no_balance)
        if records:
            ins, mod = upsert_records(records, coll)
            total_ins += ins
            total_mod += mod
            if i % 50 == 0 or i <= 5:
                logger.info(
                    f"[{i:4}/{total}] {symbol}: {len(records)} 季  "
                    f"(累計新增 {total_ins:,} / 更新 {total_mod:,})"
                )
        else:
            total_skip += 1
            if i % 50 == 0 or i <= 5:
                logger.info(f"[{i:4}/{total}] {symbol}: 無資料（累計跳過 {total_skip}）")

        if i < total:
            time.sleep(args.delay)

    # 最終統計
    logger.info('')
    logger.info('=' * 50)
    logger.info(f'下載完成！共處理 {total} 支')
    logger.info(f'  新增: {total_ins:,} 筆')
    logger.info(f'  更新: {total_mod:,} 筆')
    logger.info(f'  無資料: {total_skip} 支')

    # 季度統計
    agg = list(coll.aggregate([
        {'$group': {'_id': {'year': '$year', 'season': '$season'},
                    'count': {'$sum': 1}}},
        {'$sort':  {'_id.year': -1, '_id.season': -1}},
        {'$limit': 8},
    ]))
    logger.info('\n最近各季累積筆數：')
    for r in agg:
        logger.info(f"  {r['_id']['year']}Q{r['_id']['season']}: {r['count']:,} 支")

    client.close()


if __name__ == '__main__':
    main()
