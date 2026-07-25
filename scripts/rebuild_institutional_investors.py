#!/usr/bin/env python3
"""
重建個股三大法人買賣超資料 (institutional_investors 系列)

背景見記憶 institutional-investors-table-is-broken.md:
  - 舊 institutional_investors 84% 全零 + 16% 另一套 schema，不可用
  - 舊 institutional_trading 僅 470 檔、name 分布歪斜，不可用
  - 正確資料集是 TaiwanStockInstitutionalInvestorsBuySell（非 ...InstitutionalInvestors，後者 422）

設計要點（刻意避開 scripts/download_missing_data.py 的兩個坑）：
  1. 遇 402 配額不 break，改為等待重試 —— 舊腳本 break 導致只覆蓋 338/2442 檔
  2. 不使用裸 continue 吞例外 —— 每一檔的成敗都寫進 progress 集合，可稽核

輸出：
  institutional_investors_long  原始五類長表 {date, stock_id, name, buy, sell, net}
  institutional_investors_wide  三組寬表 {date, stock_id, foreign_net, trust_net,
                                          dealer_net, total_net, raw:{五類 net}}
  institutional_rebuild_progress  每檔進度 {_id: stock_id, status, ...}

可中斷續跑：重跑時自動略過 status 為 ok/empty 的股票。
"""

import os
import re
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient, UpdateOne, ASCENDING

PROJECT = Path('/home/mdsadmin/Stock/tw-stock-analysis')
API_URL = 'https://api.finmindtrade.com/api/v4/data'
DATASET = 'TaiwanStockInstitutionalInvestorsBuySell'

START_DATE = '2000-01-01'

# 配額：FinMind 600 次/小時，但每小時 :05 的 hourly_data_update.sh 也吃同一份配額，
# 故留約 100 次/小時的餘裕，目標 ~500 次/小時 = 7.2 秒/次。
MIN_INTERVAL = float(os.getenv('REBUILD_MIN_INTERVAL', '7.2'))
QUOTA_SLEEP = int(os.getenv('REBUILD_QUOTA_SLEEP', '300'))   # 遇 402 等待秒數
MAX_QUOTA_RETRY = int(os.getenv('REBUILD_MAX_QUOTA_RETRY', '40'))
HTTP_TIMEOUT = 60

# 六類 -> 三組的對應。
# 注意：此對應無法從現有資料反推（舊表全為 0），是人為決定，2026-07-19 由使用者確認。
# 原始六類數值一律保留在 long 表與 wide.raw，日後要改分組不必重抓。
#
# 類別隨時間演變（2026-07-19 以 2330 全區間實測）：
#   Dealer              2012-05-02 ~ 2014-11-28   自營商未拆分
#   Dealer_self         2014-12-01 起             自營商拆為自行買賣
#   Dealer_Hedging      2014-12-01 起             自營商拆為避險
#   Foreign_Dealer_Self 2017-12-18 起             外資自營商另立
# Dealer 與 Dealer_self/Hedging 重疊 0 天，併入同組不會重複計算。
# 2017-12-18 之前 Foreign_Investor 即為外資合計，故 foreign 組跨期語意一致。
GROUP_MAP = {
    'Foreign_Investor':    'foreign',
    'Foreign_Dealer_Self': 'foreign',
    'Investment_Trust':    'trust',
    'Dealer':              'dealer',
    'Dealer_self':         'dealer',
    'Dealer_Hedging':      'dealer',
}
KNOWN_NAMES = set(GROUP_MAP)


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def load_token():
    for line in (PROJECT / '.env').read_text().splitlines():
        if line.strip().startswith('FINMIND_API_TOKEN'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    raise SystemExit('FINMIND_API_TOKEN 不在 .env 中')


def to_utc_midnight(datestr):
    """與 institutional_flow / stock_price 一致：UTC 午夜 Date 型別。
    刻意不存字串，避免記憶 date-field-three-representations 記載的混型問題。"""
    y, m, d = (int(x) for x in datestr.split('-'))
    return datetime(y, m, d, tzinfo=timezone.utc)


def fetch(session, token, stock_id, end_date):
    """回傳 (rows, note)。配額耗盡會等待重試，不放棄該檔。"""
    params = {
        'dataset': DATASET,
        'data_id': stock_id,
        'start_date': START_DATE,
        'end_date': end_date,
        'token': token,
    }
    for attempt in range(MAX_QUOTA_RETRY):
        try:
            r = session.get(API_URL, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            # 網路層錯誤：短暫退避後重試，不計入配額重試上限的語意但共用計數
            log(f'  {stock_id} 網路錯誤 ({e.__class__.__name__})，30 秒後重試')
            time.sleep(30)
            continue

        if r.status_code == 200:
            body = r.json()
            if body.get('msg') == 'success' or 'data' in body:
                return body.get('data', []), None
            return [], f'200 但非 success: {str(body)[:200]}'

        if r.status_code in (402, 429):
            log(f'  {stock_id} 配額用盡 (HTTP {r.status_code})，等待 {QUOTA_SLEEP}s '
                f'(第 {attempt + 1}/{MAX_QUOTA_RETRY} 次)')
            time.sleep(QUOTA_SLEEP)
            continue

        # 其他 HTTP 錯誤：明確回報，不靜默吞掉
        return None, f'HTTP {r.status_code}: {r.text[:200]}'

    return None, f'配額重試 {MAX_QUOTA_RETRY} 次仍失敗'


def build_wide(stock_id, rows):
    """長表 -> 寬表。保留五類原始 net 於 raw。"""
    by_date = {}
    for row in rows:
        name = row.get('name')
        if name not in KNOWN_NAMES:
            # 出現未知類別要讓它浮出來，不當作 0 處理
            raise ValueError(f'{stock_id} 出現未知 name={name!r}')
        buy = row.get('buy') or 0
        sell = row.get('sell') or 0
        d = by_date.setdefault(row['date'], {'raw': {}, 'foreign': 0, 'trust': 0, 'dealer': 0})
        net = buy - sell
        d['raw'][name] = {'buy': buy, 'sell': sell, 'net': net}
        d[GROUP_MAP[name]] += net

    docs = []
    for datestr, v in by_date.items():
        total = v['foreign'] + v['trust'] + v['dealer']
        docs.append({
            'date': to_utc_midnight(datestr),
            'stock_id': stock_id,
            'foreign_net': v['foreign'],
            'trust_net': v['trust'],
            'dealer_net': v['dealer'],
            'total_net': total,
            'raw': v['raw'],
            'source': DATASET,
        })
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='只處理前 N 檔（試跑用）')
    ap.add_argument('--only', default='', help='只處理指定股票代碼，逗號分隔（試跑用）')
    ap.add_argument('--redo-errors', action='store_true', help='一併重跑先前 error 的股票')
    args = ap.parse_args()

    token = load_token()
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']

    long_col = db['institutional_investors_long']
    wide_col = db['institutional_investors_wide']
    prog_col = db['institutional_rebuild_progress']

    long_col.create_index([('stock_id', ASCENDING), ('date', ASCENDING), ('name', ASCENDING)],
                          unique=True, name='uniq_stock_date_name')
    long_col.create_index([('date', ASCENDING)], name='by_date')
    wide_col.create_index([('stock_id', ASCENDING), ('date', ASCENDING)],
                          unique=True, name='uniq_stock_date')
    wide_col.create_index([('date', ASCENDING)], name='by_date')

    end_date = datetime.now().strftime('%Y-%m-%d')

    if args.only:
        universe = [s.strip() for s in args.only.split(',') if s.strip()]
    else:
        # 股票池 = taiwan_stock_info ∪ institutional_flow 既有代碼。
        #
        # 2026-07-19 修正：原本只取 4-5 碼，理由寫「排除 132 檔權證」——這是錯的。
        # taiwan_stock_info 裡的 132 檔 6 碼全是 ETF（006203 元大MSCI台灣、
        # 006208 富邦台50、009800 中信NASDAQ …），每檔都有 700~800 筆法人資料。
        # 真正的權證是 stock_price 裡約 13,000 檔 6 碼，本來就不在 taiwan_stock_info。
        # 兩者都是 6 碼但屬於完全不同的母體，不可用位數一概而論。
        #
        # 另有 13 檔（0050、009818~009825、020016、2325、2856、4944）存在於
        # institutional_flow 卻不在 taiwan_stock_info（主檔缺漏），故取聯集補回。
        pat = re.compile(r'^[0-9]{4,6}[A-Z]?$')
        pool = {s for s in db.taiwan_stock_info.distinct('stock_id') if s and pat.match(s)}
        pool |= {s for s in db.institutional_flow.distinct('stock_id') if s and pat.match(s)}
        universe = sorted(pool)

    done_statuses = ['ok', 'empty'] if args.redo_errors else ['ok', 'empty', 'error']
    done = set(prog_col.distinct('_id', {'status': {'$in': done_statuses}}))
    todo = [s for s in universe if s not in done]
    if args.limit:
        todo = todo[:args.limit]

    log(f'股票池 {len(universe)} 檔，已完成 {len(done)} 檔，本次待處理 {len(todo)} 檔')
    log(f'節流 {MIN_INTERVAL}s/次 → 預估 {len(todo) * MIN_INTERVAL / 3600:.1f} 小時（不含配額等待）')

    session = requests.Session()
    stat = {'ok': 0, 'empty': 0, 'error': 0, 'long_rows': 0, 'wide_rows': 0}
    t_start = time.time()

    for i, stock_id in enumerate(todo, 1):
        t0 = time.time()
        rows, note = fetch(session, token, stock_id, end_date)

        if rows is None:
            stat['error'] += 1
            prog_col.update_one({'_id': stock_id},
                                {'$set': {'status': 'error', 'error': note,
                                          'fetched_at': datetime.now(timezone.utc)}},
                                upsert=True)
            log(f'[{i}/{len(todo)}] {stock_id} ERROR {note}')
        elif not rows:
            stat['empty'] += 1
            prog_col.update_one({'_id': stock_id},
                                {'$set': {'status': 'empty', 'long_rows': 0, 'wide_rows': 0,
                                          'fetched_at': datetime.now(timezone.utc)}},
                                upsert=True)
        else:
            try:
                wide_docs = build_wide(stock_id, rows)
            except ValueError as e:
                stat['error'] += 1
                prog_col.update_one({'_id': stock_id},
                                    {'$set': {'status': 'error', 'error': str(e),
                                              'fetched_at': datetime.now(timezone.utc)}},
                                    upsert=True)
                log(f'[{i}/{len(todo)}] {stock_id} ERROR {e}')
                _throttle(t0)
                continue

            long_ops = [
                UpdateOne(
                    {'stock_id': stock_id, 'date': to_utc_midnight(r['date']), 'name': r['name']},
                    {'$set': {'buy': r.get('buy') or 0,
                              'sell': r.get('sell') or 0,
                              'net': (r.get('buy') or 0) - (r.get('sell') or 0),
                              'source': DATASET}},
                    upsert=True)
                for r in rows
            ]
            wide_ops = [
                UpdateOne({'stock_id': d['stock_id'], 'date': d['date']},
                          {'$set': d}, upsert=True)
                for d in wide_docs
            ]
            long_col.bulk_write(long_ops, ordered=False)
            wide_col.bulk_write(wide_ops, ordered=False)

            stat['ok'] += 1
            stat['long_rows'] += len(rows)
            stat['wide_rows'] += len(wide_docs)
            prog_col.update_one({'_id': stock_id},
                                {'$set': {'status': 'ok',
                                          'long_rows': len(rows),
                                          'wide_rows': len(wide_docs),
                                          'fetched_at': datetime.now(timezone.utc)},
                                 '$unset': {'error': ''}},
                                upsert=True)

        if i % 25 == 0 or i == len(todo):
            el = time.time() - t_start
            rate = i / el * 3600 if el else 0
            eta = (len(todo) - i) / (i / el) / 3600 if i and el else 0
            log(f'[{i}/{len(todo)}] ok={stat["ok"]} empty={stat["empty"]} err={stat["error"]} '
                f'long={stat["long_rows"]:,} wide={stat["wide_rows"]:,} '
                f'| {rate:.0f} 檔/小時 | 剩餘約 {eta:.1f} 小時')

        _throttle(t0)

    log('=' * 70)
    log(f'完成：ok={stat["ok"]} empty={stat["empty"]} error={stat["error"]}')
    log(f'寫入 long {stat["long_rows"]:,} 列 / wide {stat["wide_rows"]:,} 列')
    log(f'集合總量 long={long_col.estimated_document_count():,} '
        f'wide={wide_col.estimated_document_count():,}')
    if stat['error']:
        log(f'有 {stat["error"]} 檔失敗，重跑： --redo-errors')
    log('=' * 70)


def _throttle(t0):
    remain = MIN_INTERVAL - (time.time() - t0)
    if remain > 0:
        time.sleep(remain)


if __name__ == '__main__':
    main()
