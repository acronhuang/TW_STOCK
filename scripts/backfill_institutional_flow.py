#!/usr/bin/env python3
"""
回填 institutional_flow 上市股欄位錯位（見記憶 institutional-flow-t86-column-shift）

資料源：institutional_investors_wide（由 rebuild_institutional_investors.py 重建，
        已與 TWSE 官方 T86 原始欄位逐欄對帳吻合）

只修 data_source == 'TWSE_T86' 的列。TPEX_3INSTI 走 OpenAPI 具名欄位、原本就正確，
刻意不動，以免用另一套定義覆蓋掉正確資料。

預設 dry-run，需明確加 --execute 才會寫入。
"""

import argparse
import sys
from datetime import datetime, timezone

from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

BATCH = 5000
SOURCE_FILTER = 'TWSE_T86'


def dec(v):
    return Decimal128(str(float(v)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true', help='實際寫入（預設只試算）')
    ap.add_argument('--limit', type=int, default=0, help='只處理前 N 筆 wide（測試用）')
    args = ap.parse_args()

    db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
    flow = db.institutional_flow
    wide = db.institutional_investors_wide

    # 只需處理 flow 涵蓋的時間範圍
    lo = flow.find_one({'data_source': SOURCE_FILTER}, sort=[('date', 1)], projection={'date': 1})
    hi = flow.find_one({'data_source': SOURCE_FILTER}, sort=[('date', -1)], projection={'date': 1})
    if not lo:
        print('institutional_flow 沒有 TWSE_T86 資料，結束')
        return 1
    lo, hi = lo['date'], hi['date']
    print(f'flow TWSE_T86 範圍：{lo.date()} ~ {hi.date()}')
    print(f'flow TWSE_T86 筆數：{flow.count_documents({"data_source": SOURCE_FILTER}):,}')
    print(f'模式：{"實際寫入" if args.execute else "DRY RUN（不寫入）"}')
    print('-' * 60)

    cur = wide.find({'date': {'$gte': lo, '$lte': hi}},
                    {'stock_id': 1, 'date': 1, 'foreign_net': 1, 'trust_net': 1,
                     'dealer_net': 1, 'total_net': 1, 'raw': 1}).batch_size(BATCH)
    if args.limit:
        cur = cur.limit(args.limit)

    ops, filters, scanned, matched, modified = [], [], 0, 0, 0
    now = datetime.now(timezone.utc)

    def flush():
        nonlocal ops, filters, matched, modified
        if not ops:
            return
        if args.execute:
            res = flow.bulk_write(ops, ordered=False)
            matched += res.matched_count
            modified += res.modified_count
        else:
            # dry-run：用 $or 一次算這批會命中幾筆，不寫入
            matched += flow.count_documents({'$or': filters})
        ops, filters = [], []

    for d in cur:
        scanned += 1
        raw = d.get('raw', {})

        def rawnet(name):
            e = raw.get(name)
            return e['net'] if e else 0

        filt = {'stock_id': d['stock_id'], 'date': d['date'], 'data_source': SOURCE_FILTER}
        filters.append(filt)
        ops.append(UpdateOne(
            filt,
            {'$set': {
                'foreign_net': dec(d['foreign_net']),
                'trust_net':   dec(d['trust_net']),
                'dealer_net':  dec(d['dealer_net']),
                'total_net':   dec(d['total_net']),
                'foreign_investor_net':    dec(rawnet('Foreign_Investor')),
                'foreign_dealer_self_net': dec(rawnet('Foreign_Dealer_Self')),
                'dealer_self_net':         dec(rawnet('Dealer_self')),
                'dealer_hedging_net':      dec(rawnet('Dealer_Hedging')),
                'backfilled_at': now,
                'backfill_source': 'institutional_investors_wide',
            }}))

        if len(ops) >= BATCH:
            flush()
            print(f'  已掃描 wide {scanned:,} 筆 | 命中 flow {matched:,} 筆', flush=True)

    flush()
    print('-' * 60)
    print(f'掃描 wide {scanned:,} 筆')
    print(f'命中 flow {matched:,} 筆')
    if args.execute:
        print(f'實際修改 {modified:,} 筆')
        remain = flow.count_documents({'data_source': SOURCE_FILTER,
                                       'backfilled_at': {'$exists': False}})
        print(f'仍未回填的 TWSE_T86 列：{remain:,}'
              + ('  ← wide 無對應資料，需查明' if remain else '  ✅'))
    else:
        print('（DRY RUN，未寫入。確認無誤後加 --execute）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
