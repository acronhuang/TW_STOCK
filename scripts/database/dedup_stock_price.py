"""
stock_price 集合去重腳本

問題：stock_price 集合存在約 669K 重複 (stock_id, date) 記錄（佔 13%），
     會導致下游分析產生重複型態信號。

做法：
    1. 用 $group 聚合找出所有重複 (stock_id, date) 組
    2. 每組保留最新 _id（最後插入），刪除其餘
    3. 建立唯一複合索引防止未來重複

用法：
    python scripts/database/dedup_stock_price.py [--dry-run]

Author: SenVision Team
Date: 2026-02-27
"""

import argparse
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError


def main():
    parser = argparse.ArgumentParser(description='去重 stock_price 集合')
    parser.add_argument('--dry-run', action='store_true',
                        help='只統計不刪除')
    parser.add_argument('--uri', default='mongodb://localhost:27017',
                        help='MongoDB URI')
    parser.add_argument('--db', default='tw_stock_analysis',
                        help='資料庫名稱')
    args = parser.parse_args()

    client = MongoClient(args.uri)
    db = client[args.db]
    coll = db['stock_price']

    print(f'連線: {args.uri} / {args.db}')
    total_before = coll.count_documents({})
    print(f'stock_price 總筆數: {total_before:,}')

    # Step 1: 找出重複組
    pipeline = [
        {'$group': {
            '_id': {'stock_id': '$stock_id', 'date': '$date'},
            'count': {'$sum': 1},
            'ids': {'$push': '$_id'},
        }},
        {'$match': {'count': {'$gt': 1}}},
    ]

    print('\n掃描重複記錄...')
    dup_groups = list(coll.aggregate(pipeline, allowDiskUse=True))
    dup_count = sum(g['count'] - 1 for g in dup_groups)
    print(f'發現 {len(dup_groups):,} 組重複，共 {dup_count:,} 筆待刪除')

    if dup_count == 0:
        print('無重複記錄，跳過刪除')
    elif args.dry_run:
        print('[DRY RUN] 不執行刪除')
        # 印出前 10 組示例
        for g in dup_groups[:10]:
            sid = g['_id']['stock_id']
            d = g['_id']['date']
            print(f'  {sid} / {d} → {g["count"]} 筆')
        if len(dup_groups) > 10:
            print(f'  ... 及其他 {len(dup_groups) - 10} 組')
    else:
        # Step 2: 每組保留最後一筆（ids[-1]），刪除 ids[:-1]
        print('\n開始刪除...')
        total_deleted = 0
        batch_ids = []
        batch_size = 5000

        for g in dup_groups:
            to_remove = g['ids'][:-1]  # 保留最後插入的
            batch_ids.extend(to_remove)

            if len(batch_ids) >= batch_size:
                result = coll.delete_many({'_id': {'$in': batch_ids}})
                total_deleted += result.deleted_count
                print(f'  已刪除 {total_deleted:,} / {dup_count:,}')
                batch_ids = []

        # 處理剩餘
        if batch_ids:
            result = coll.delete_many({'_id': {'$in': batch_ids}})
            total_deleted += result.deleted_count

        print(f'\n刪除完成：共刪除 {total_deleted:,} 筆')
        total_after = coll.count_documents({})
        print(f'刪除前: {total_before:,} → 刪除後: {total_after:,}')

    # Step 3+4: 建立唯一索引並驗證（僅在非 dry-run 時執行）
    if args.dry_run:
        print(f'\n[DRY RUN] 跳過索引建立與驗證。')
        print(f'若確認無誤，請移除 --dry-run 重新執行以實際刪除。')
    else:
        print('\n建立唯一複合索引 (stock_id, date)...')
        try:
            coll.create_index(
                [('stock_id', 1), ('date', 1)],
                unique=True,
                name='idx_stock_date_unique',
            )
            print('索引建立成功')
        except DuplicateKeyError:
            print('ERROR: 仍有重複記錄，無法建立唯一索引。請重新執行去重。')
            sys.exit(1)
        except Exception as e:
            if 'already exists' in str(e):
                print('唯一索引已存在')
            else:
                raise

        print('\n驗證...')
        verify_pipeline = [
            {'$group': {
                '_id': {'stock_id': '$stock_id', 'date': '$date'},
                'count': {'$sum': 1},
            }},
            {'$match': {'count': {'$gt': 1}}},
            {'$count': 'dup_groups'},
        ]
        result = list(coll.aggregate(verify_pipeline, allowDiskUse=True))
        remaining = result[0]['dup_groups'] if result else 0
        print(f'剩餘重複組數: {remaining}')

        if remaining == 0:
            print('\n去重完成，stock_price 集合已清理乾淨。')
        else:
            print(f'\nWARNING: 仍有 {remaining} 組重複！')

    client.close()


if __name__ == '__main__':
    main()
