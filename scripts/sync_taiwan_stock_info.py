#!/usr/bin/env python3
"""
同步 taiwan_stock_info 主檔（FinMind TaiwanStockInfo）

2026-07-19 建立。起因見記憶 taiwan-stock-info-gaps：
  - 主檔停在 2026-02-20 達五個月，缺 71 檔（含 0050 元大台灣50）
  - 根因：32 列類股指數的 date 被寫成字串 "None"，而 'N' > '2'，
    使 _has_recent_data 的 sort(date,-1) 取到 "None" 並判定
    "None" >= "2026-07-19" 為 True → 整張表永久跳過下載
  - 另有 369 個重複代碼（3,453 列 / 3,047 去重），因 config 宣告的
    unique_keys=["stock_id"] 從未建立成唯一索引

本腳本以 stock_id 為鍵 upsert（同一代碼保留 date 最新者），
並把 date 為 "None"/空字串者正規化為 None，避免再次鎖死排序。

預設 dry-run，需 --execute 才寫入。
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient, UpdateOne

PROJECT = Path('/home/mdsadmin/Stock/tw-stock-analysis')
API_URL = 'https://api.finmindtrade.com/api/v4/data'


def load_token():
    for line in (PROJECT / '.env').read_text().splitlines():
        if line.strip().startswith('FINMIND_API_TOKEN'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    raise SystemExit('FINMIND_API_TOKEN 不在 .env 中')


def clean_date(v):
    """把 'None' / '' / None 一律正規化為 None，其餘保留原字串。"""
    if v is None:
        return None
    s = str(v).strip()
    if s in ('', 'None', 'null', 'NaT'):
        return None
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true', help='實際寫入（預設只試算）')
    ap.add_argument('--dedupe', action='store_true',
                    help='一併清除同代碼的重複列（只留 upsert 後的那筆）')
    args = ap.parse_args()

    db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
    col = db.taiwan_stock_info

    before_rows = col.count_documents({})
    before_ids = len(col.distinct('stock_id'))
    print(f'現況：{before_rows:,} 列 / {before_ids:,} 檔')

    r = requests.get(API_URL, params={'dataset': 'TaiwanStockInfo',
                                      'token': load_token()}, timeout=90)
    if r.status_code != 200:
        raise SystemExit(f'下載失敗 HTTP {r.status_code}: {r.text[:200]}')
    data = r.json().get('data', [])
    print(f'上游：{len(data):,} 列 / {len({x["stock_id"] for x in data}):,} 檔')

    # 同一 stock_id 可能有多列（不同 date），保留 date 最新者
    best = {}
    for x in data:
        sid = x.get('stock_id')
        if not sid:
            continue
        d = clean_date(x.get('date'))
        cur = best.get(sid)
        if cur is None or (d or '') > (clean_date(cur.get('date')) or ''):
            best[sid] = x

    local_ids = set(col.distinct('stock_id'))
    added = sorted(set(best) - local_ids)
    print(f'將新增 {len(added)} 檔' + (f'：{", ".join(added[:20])}' if added else ''))
    print(f'0050 在新增清單中: {"0050" in added}')

    if not args.execute:
        print('\n（DRY RUN，未寫入。確認無誤後加 --execute）')
        return 0

    now = datetime.now(timezone.utc)
    ops = []
    for sid, x in best.items():
        doc = {k: v for k, v in x.items() if k != '_id'}
        doc['date'] = clean_date(doc.get('date'))
        doc['info_synced_at'] = now
        ops.append(UpdateOne({'stock_id': sid}, {'$set': doc}, upsert=True))

    res = col.bulk_write(ops, ordered=False)
    print(f'\nupsert：新增 {res.upserted_count}、更新 {res.modified_count}')

    # 既有的 "None" 字串一併正規化（含未被上游覆蓋到的舊列）
    fixed = col.update_many({'date': {'$in': ['None', '', 'null']}},
                            {'$set': {'date': None}})
    print(f'正規化 date="None" 的舊列：{fixed.modified_count} 列')

    if args.dedupe:
        removed = 0
        for sid in col.distinct('stock_id'):
            docs = list(col.find({'stock_id': sid}, {'_id': 1, 'info_synced_at': 1})
                        .sort('info_synced_at', -1))
            for d in docs[1:]:
                col.delete_one({'_id': d['_id']})
                removed += 1
        print(f'去重刪除：{removed} 列')

    after_rows = col.count_documents({})
    after_ids = len(col.distinct('stock_id'))
    print(f'結果：{before_rows:,} → {after_rows:,} 列 / {before_ids:,} → {after_ids:,} 檔')
    print(f'0050 現況：{col.find_one({"stock_id": "0050"}) is not None}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
