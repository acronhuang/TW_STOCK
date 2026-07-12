#!/usr/bin/env python3
"""
批量下載股票價格數據

使用範例:
    # 從文件讀取股票列表
    python3 scripts/download_stock_prices.py --stock-list /tmp/stock_list.txt --start-date 2022-01-01 --end-date 2024-12-31
    
    # 指定單一股票
    python3 scripts/download_stock_prices.py --stock-id 2330 --start-date 2022-01-01 --end-date 2024-12-31
    
    # 批量下載（使用 workers）
    python3 scripts/download_stock_prices.py --stock-list /tmp/stock_list.txt --workers 4 --start-date 2022-01-01 --end-date 2024-12-31
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from pymongo import MongoClient
from typing import List, Set
import time

# 設定路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.downloaders.finmind_client import FinMindClient


def load_stock_list(file_path: str) -> List[str]:
    """
    從文件讀取股票列表
    支持格式：
    - 每行一個股票代碼
    - JSON 數組 ["2330", "2317", ...]
    - MongoDB 輸出格式（多行數組）
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        
        # 嘗試解析 JSON（移除換行符合併多行）
        if content.startswith('['):
            try:
                # 移除換行符和多餘空格，合併成單行 JSON
                content_clean = content.replace('\n', '').replace('\r', '')
                stock_list = json.loads(content_clean)
                return [str(s).strip().strip('"\'') for s in stock_list if s]
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON 解析失敗: {e}")
                pass
        
        # 否則按行讀取
        lines = content.split('\n')
        stock_list = []
        for line in lines:
            line = line.strip().strip('"\'')
            if line and not line.startswith('#') and not line.startswith('[') and not line.startswith(']'):
                stock_list.append(line)
        
        return stock_list


def get_existing_stocks(db, stock_ids: List[str], start_date: str, end_date: str) -> Set[str]:
    """
    檢查哪些股票已經有完整的價格數據
    """
    existing = set()
    total_days = (datetime.strptime(end_date, '%Y-%m-%d') - 
                  datetime.strptime(start_date, '%Y-%m-%d')).days
    
    print(f"\n🔍 檢查已存在的數據...")
    for stock_id in stock_ids:
        count = db.stock_price.count_documents({
            'stock_id': stock_id,
            'date': {'$gte': start_date, '$lte': end_date}
        })
        
        # 如果記錄數 >= 總天數的 60%，認為數據完整
        if count >= total_days * 0.6:
            existing.add(stock_id)
    
    return existing


def download_stock_price(client: FinMindClient, db, stock_id: str, 
                         start_date: str, end_date: str, force: bool = False) -> dict:
    """
    下載單一股票的價格數據
    """
    result = {
        'stock_id': stock_id,
        'success': False,
        'new_records': 0,
        'updated_records': 0,
        'skipped_records': 0,
        'error': None
    }
    
    try:
        # 檢查是否已存在
        if not force:
            existing_count = db.stock_price.count_documents({
                'stock_id': stock_id,
                'date': {'$gte': start_date, '$lte': end_date}
            })
            
            # 如果已有數據，跳過
            total_days = (datetime.strptime(end_date, '%Y-%m-%d') - 
                         datetime.strptime(start_date, '%Y-%m-%d')).days
            if existing_count >= total_days * 0.6:
                result['skipped_records'] = existing_count
                result['success'] = True
                return result
        
        # 調用 FinMind API
        data = client.fetch_data(
            dataset='TaiwanStockPrice',
            params={
                'data_id': stock_id,
                'start_date': start_date,
                'end_date': end_date
            }
        )
        
        if not data:
            result['error'] = '無數據'
            return result
        
        # 批量寫入數據庫
        from pymongo import UpdateOne
        operations = []
        
        for record in data:
            # 標準化字段名稱
            from bson import Decimal128
            
            def to_decimal(value):
                """轉換為 Decimal128"""
                if isinstance(value, Decimal128):
                    return value
                if value is None or value == '':
                    return Decimal128('0')
                return Decimal128(str(value))
            
            def to_int(value):
                """安全轉換為整數"""
                if isinstance(value, Decimal128):
                    return int(value.to_decimal())
                if value is None or value == '':
                    return 0
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    return 0
            
            doc = {
                'stock_id': stock_id,
                'date': record.get('date'),
                'open': to_decimal(record.get('open', 0)),
                'high': to_decimal(record.get('max', 0)),
                'low': to_decimal(record.get('min', 0)),
                'close': to_decimal(record.get('close', 0)),
                'volume': to_int(record.get('Trading_Volume', 0)),
                'turnover': to_decimal(record.get('Trading_money', 0)),
                'updated_at': datetime.now()
            }
            
            # 使用 upsert 避免重複
            operations.append(
                UpdateOne(
                    {'stock_id': stock_id, 'date': doc['date']},
                    {'$set': doc},
                    upsert=True
                )
            )
        
        # 執行批量寫入
        if operations:
            write_result = db.stock_price.bulk_write(operations)
            result['new_records'] = write_result.upserted_count
            result['updated_records'] = write_result.modified_count
        
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='批量下載股票價格數據',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  從文件讀取股票列表:
    python3 scripts/download_stock_prices.py --stock-list /tmp/stock_list.txt --start-date 2022-01-01 --end-date 2024-12-31
  
  指定單一股票:
    python3 scripts/download_stock_prices.py --stock-id 2330 --start-date 2022-01-01 --end-date 2024-12-31
  
  強制覆蓋:
    python3 scripts/download_stock_prices.py --stock-list /tmp/stock_list.txt --start-date 2022-01-01 --end-date 2024-12-31 --force
        """
    )
    
    parser.add_argument(
        '--stock-list',
        help='股票列表文件路徑（每行一個股票代碼或 JSON 數組）'
    )
    
    parser.add_argument(
        '--stock-id',
        help='單一股票代碼'
    )
    
    parser.add_argument(
        '--start-date',
        required=True,
        help='開始日期 (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end-date',
        required=True,
        help='結束日期 (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='強制覆蓋已存在的數據'
    )
    
    parser.add_argument(
        '--mongo-uri',
        default='mongodb://localhost:27017/',
        help='MongoDB 連線 URI'
    )
    
    parser.add_argument(
        '--db-name',
        default='tw_stock_analysis',
        help='資料庫名稱'
    )
    
    args = parser.parse_args()
    
    # 驗證參數
    if not args.stock_list and not args.stock_id:
        parser.error("必須指定 --stock-list 或 --stock-id")
    
    # 獲取 API Token
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 錯誤: 未設定 FINMIND_API_TOKEN 環境變數")
        print("\n請執行: export FINMIND_API_TOKEN='your_token_here'")
        sys.exit(1)
    
    # 讀取股票列表
    if args.stock_list:
        print(f"📂 讀取股票列表: {args.stock_list}")
        stock_ids = load_stock_list(args.stock_list)
    else:
        stock_ids = [args.stock_id]
    
    print(f"✅ 共 {len(stock_ids)} 支股票")
    
    # 連接數據庫
    print(f"\n🔌 連接 MongoDB: {args.mongo_uri}")
    client_mongo = MongoClient(args.mongo_uri)
    db = client_mongo[args.db_name]
    
    # 初始化 FinMind 客戶端
    print(f"🔑 初始化 FinMind 客戶端...")
    finmind = FinMindClient(api_token)
    
    # 檢查已存在的數據
    if not args.force:
        existing_stocks = get_existing_stocks(db, stock_ids, args.start_date, args.end_date)
        if existing_stocks:
            print(f"⏭️  {len(existing_stocks)} 支股票已有完整數據，將跳過")
            stock_ids = [s for s in stock_ids if s not in existing_stocks]
    
    print(f"\n📊 開始下載 {len(stock_ids)} 支股票的價格數據")
    print(f"📅 日期範圍: {args.start_date} ~ {args.end_date}")
    print(f"{'='*80}\n")
    
    # 統計資訊
    stats = {
        'total': len(stock_ids),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'new_records': 0,
        'updated_records': 0,
        'errors': []
    }
    
    start_time = datetime.now()
    
    # 逐一下載
    for i, stock_id in enumerate(stock_ids, 1):
        print(f"[{i}/{len(stock_ids)}] 下載 {stock_id}...", end=' ', flush=True)
        
        result = download_stock_price(
            finmind, db, stock_id,
            args.start_date, args.end_date,
            force=args.force
        )
        
        if result['success']:
            if result['skipped_records'] > 0:
                print(f"⏭️  已存在 {result['skipped_records']} 條記錄")
                stats['skipped'] += 1
            else:
                print(f"✅ 新增 {result['new_records']} 條，更新 {result['updated_records']} 條")
                stats['success'] += 1
                stats['new_records'] += result['new_records']
                stats['updated_records'] += result['updated_records']
        else:
            print(f"❌ {result['error']}")
            stats['failed'] += 1
            stats['errors'].append({
                'stock_id': stock_id,
                'error': result['error']
            })
        
        # API 限流：每秒最多 2 次請求
        time.sleep(0.6)
    
    # 輸出統計
    duration = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'='*80}")
    print("📊 下載完成統計")
    print(f"{'='*80}")
    print(f"總股票數:         {stats['total']}")
    print(f"成功下載:         {stats['success']}")
    print(f"跳過 (已存在):    {stats['skipped']}")
    print(f"下載失敗:         {stats['failed']}")
    print(f"─" * 80)
    print(f"新增記錄:         {stats['new_records']:,}")
    print(f"更新記錄:         {stats['updated_records']:,}")
    print(f"─" * 80)
    print(f"耗時:             {duration:.2f} 秒")
    print(f"平均每支股票:     {duration/len(stock_ids):.2f} 秒")
    print(f"{'='*80}\n")
    
    # 輸出錯誤詳情
    if stats['errors']:
        print("❌ 錯誤詳情:")
        for error in stats['errors'][:10]:  # 只顯示前 10 個
            print(f"  - {error['stock_id']}: {error['error']}")
        if len(stats['errors']) > 10:
            print(f"  ... 還有 {len(stats['errors']) - 10} 個錯誤")
        print()
    
    # 檢查數據覆蓋情況
    total_stocks_with_price = db.stock_price.distinct('stock_id')
    print(f"✅ 數據庫現有價格數據: {len(total_stocks_with_price)} 支股票")
    
    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
