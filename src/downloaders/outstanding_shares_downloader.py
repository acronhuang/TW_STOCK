#!/usr/bin/env python3
"""
P2-B: 流通股数下载器

从 FinMind TaiwanStockBalanceSheet API 下载股本数据并更新 outstanding_shares

数据来源: TaiwanStockBalanceSheet -> CapitalStock (股本合計)
计算公式: outstanding_shares = CapitalStock / 10 (台湾股票面额为 10 元/股)

储存到: taiwan_stock_info.outstanding_shares (单位:千股)

执行方式:
    # 单一股票
    python3 src/downloaders/outstanding_shares_downloader.py --stock-id 2330 --dry-run
    
    # 所有股票
    python3 src/downloaders/outstanding_shares_downloader.py --all --execute
    
    # 优先列表（核心 50 支股票）
    python3 src/downloaders/outstanding_shares_downloader.py --priority-list --execute
    
    # 跳过已下载（断点续传）
    python3 src/downloaders/outstanding_shares_downloader.py --all --skip-existing --execute
"""

import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
from bson.decimal128 import Decimal128
import requests
from typing import Dict, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class OutstandingSharesDownloader:
    """流通股数下载器"""
    
    def __init__(self, 
                 api_token: str = None,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        
        self.api_token = api_token or os.getenv('FINMIND_API_TOKEN')
        if not self.api_token:
            raise ValueError("请设定 FINMIND_API_TOKEN 环境变量或传入 api_token 参数")
        
        self.base_url = "https://api.finmindtrade.com/api/v4/data"
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.logger = self._setup_logger()
        
        # API 速率限制
        self.last_request_time = 0
        self.min_request_interval = 0.6  # 秒 (每分鐘最多100次)
    
    def _setup_logger(self) -> logging.Logger:
        """设定日志"""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"outstanding_shares_{timestamp}.log"
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def _rate_limit(self):
        """API 速率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _to_decimal128(self, value):
        """转换为 Decimal128"""
        if value is None:
            return None
        if isinstance(value, Decimal128):
            return value
        return Decimal128(str(Decimal(str(value))))
    
    def download_capital_stock(self, stock_id: str) -> float:
        """
        下載股本數據
        
        Args:
            stock_id: 股票代碼
            
        Returns:
            流通股數（單位：千股），如果失敗返回 0
        """
        self._rate_limit()
        
        params = {
            'dataset': 'TaiwanStockBalanceSheet',
            'data_id': stock_id,
            'start_date': '2024-01-01',  # 只要最近的数据
            'token': self.api_token
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 200:
                self.logger.error(f"API 錯誤: {data.get('msg')}")
                return 0.0
            
            records = data.get('data', [])
            
            if not records:
                self.logger.warning(f"⚠️  {stock_id}: 無資產負債表數據")
                return 0.0
            
            # 查找最新的股本数据 (CapitalStock)
            latest_date = max([r['date'] for r in records])
            
            capital_record = next(
                (r for r in records 
                 if r['date'] == latest_date and 
                 r['type'] == 'CapitalStock'),
                None
            )
            
            if not capital_record:
                self.logger.warning(f"⚠️  {stock_id}: 找不到股本數據")
                return 0.0
            
            # 股本金额（元）
            capital_amount = float(capital_record.get('value', 0))
            
            if capital_amount <= 0:
                self.logger.warning(f"⚠️  {stock_id}: 股本金額無效 = {capital_amount}")
                return 0.0
            
            # 計算流通股數
            # 台灣股票面額 = 10 元/股
            # 流通股數（股）= 股本（元）/ 面額
            # 流通股數（千股）= 流通股數（股）/ 1000
            par_value = 10
            outstanding_shares = capital_amount / par_value  # 股
            outstanding_shares_k = outstanding_shares / 1000  # 千股
            
            self.logger.info(
                f"✅ {stock_id}: 股本 {capital_amount/1e8:,.2f} 億, "
                f"流通股數 {outstanding_shares_k:,.0f} 千股 "
                f"({latest_date})"
            )
            
            return outstanding_shares_k
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ {stock_id}: API 請求失敗 - {e}")
            return 0.0
        except Exception as e:
            self.logger.error(f"❌ {stock_id}: 處理失敗 - {e}")
            return 0.0
    
    def update_stock(self, stock_id: str, dry_run: bool = True) -> Dict:
        """
        更新單一股票的流通股數
        
        Returns:
            統計信息
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"處理 {stock_id}")
        self.logger.info(f"{'='*80}")
        
        stats = {
            'stock_id': stock_id,
            'status': 'pending',
            'outstanding_shares': 0,
            'updated': False
        }
        
        try:
            # 1. 下載股本數據
            outstanding_shares_k = self.download_capital_stock(stock_id)
            
            if outstanding_shares_k <= 0:
                stats['status'] = 'no_data'
                return stats
            
            stats['outstanding_shares'] = outstanding_shares_k
            
            # 2. 更新資料庫
            if not dry_run:
                result = self.db.taiwan_stock_info.update_one(
                    {'stock_id': stock_id},
                    {
                        '$set': {
                            'outstanding_shares': self._to_decimal128(outstanding_shares_k),
                            'updated_at': datetime.now()
                        }
                    },
                    upsert=True
                )
                
                stats['updated'] = result.modified_count > 0 or result.upserted_id is not None
                stats['status'] = 'success'
                
                if stats['updated']:
                    self.logger.info(f"✅ 已更新")
                else:
                    self.logger.info(f"✅ 無需更新（值相同）")
            else:
                stats['status'] = 'dry_run'
                self.logger.info(f"✅ 預覽完成（未寫入）")
            
        except Exception as e:
            error_msg = f"處理失敗: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            stats['status'] = 'error'
            stats['error'] = error_msg
        
        return stats
    
    def _load_priority_list(self) -> List[str]:
        """
        載入優先股票列表
        
        Returns:
            股票代碼列表
        """
        priority_file = project_root / "data" / "priority_stocks.txt"
        
        if not priority_file.exists():
            self.logger.error(f"找不到優先列表: {priority_file}")
            return []
        
        stock_ids = []
        with open(priority_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 格式: 股票代碼,股票名稱,分類
                parts = line.split(',')
                if parts:
                    stock_ids.append(parts[0])
        
        self.logger.info(f"載入優先列表: {len(stock_ids)} 支股票")
        return stock_ids
    
    def _filter_existing(self, stock_ids: List[str]) -> List[str]:
        """
        過濾已有 outstanding_shares 的股票
        
        Args:
            stock_ids: 原始股票代碼列表
            
        Returns:
            未下載的股票代碼列表
        """
        # 查詢已有 outstanding_shares 的股票
        existing_stocks = self.db.taiwan_stock_info.find(
            {
                'stock_id': {'$in': stock_ids},
                'outstanding_shares': {'$exists': True, '$ne': None}
            },
            {'stock_id': 1}
        )
        
        existing_ids = {doc['stock_id'] for doc in existing_stocks}
        
        # 返回未下載的
        return [sid for sid in stock_ids if sid not in existing_ids]
    
    def update_all_stocks(self, 
                          dry_run: bool = True, 
                          limit: int = None,
                          priority_list: bool = False,
                          skip_existing: bool = False) -> Dict:
        """
        更新所有股票的流通股數
        
        Args:
            dry_run: 預覽模式
            limit: 限制處理數量
            priority_list: 使用優先股票列表（核心 50 支）
            skip_existing: 跳過已有 outstanding_shares 的股票
        
        Returns:
            總體統計
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🚀 流通股數下載器")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"模式: {'預覽模式' if dry_run else '執行模式'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 獲取股票代碼
        if priority_list:
            stock_ids = self._load_priority_list()
            self.logger.info(f"來源: 優先股票列表 (核心 50 支)")
        else:
            stock_ids = self.db.taiwan_stock_info.distinct('stock_id')
            self.logger.info(f"來源: 資料庫全部股票")
        
        # 跳過已下載
        if skip_existing:
            original_count = len(stock_ids)
            stock_ids = self._filter_existing(stock_ids)
            skipped = original_count - len(stock_ids)
            self.logger.info(f"跳過已下載: {skipped} 支")
        
        if limit:
            stock_ids = stock_ids[:limit]
            self.logger.info(f"限制數量: {limit}")
        
        self.logger.info(f"{'='*80}\n")
        self.logger.info(f"待處理股票: {len(stock_ids)} 支\n")
        
        # 統計
        total_stats = {
            'total': len(stock_ids),
            'success': 0,
            'no_data': 0,
            'error': 0,
            'updated': 0
        }
        
        # 逐一處理
        for i, stock_id in enumerate(stock_ids, 1):
            self.logger.info(f"[{i}/{len(stock_ids)}] {stock_id}")
            
            stats = self.update_stock(stock_id, dry_run)
            
            if stats['status'] == 'success' or stats['status'] == 'dry_run':
                total_stats['success'] += 1
                if stats.get('updated'):
                    total_stats['updated'] += 1
            elif stats['status'] == 'no_data':
                total_stats['no_data'] += 1
            else:
                total_stats['error'] += 1
        
        # 總結報告
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"📊 下載總結")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"股票總數: {total_stats['total']}")
        self.logger.info(f"  成功: {total_stats['success']}")
        self.logger.info(f"  無數據: {total_stats['no_data']}")
        self.logger.info(f"  錯誤: {total_stats['error']}")
        
        if not dry_run:
            self.logger.info(f"\n已更新記錄: {total_stats['updated']}")
        
        self.logger.info(f"{'='*80}")
        
        if dry_run:
            self.logger.info(f"\n⚠️  這是預覽模式")
            self.logger.info(f"{'='*80}\n")
        
        return total_stats


def main():
    parser = argparse.ArgumentParser(
        description='流通股數下載器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 預覽單一股票
  python3 %(prog)s --stock-id 2330 --dry-run
  
  # 下載優先列表（核心 50 支股票）
  python3 %(prog)s --priority-list --execute
  
  # 下載所有股票（跳過已下載）
  python3 %(prog)s --all --skip-existing --execute
  
  # 測試前 10 支
  python3 %(prog)s --all --limit 10 --dry-run
        """
    )
    parser.add_argument('--stock-id', help='單一股票代碼')
    parser.add_argument('--all', action='store_true', help='所有股票')
    parser.add_argument('--priority-list', action='store_true', 
                        help='使用優先股票列表（核心 50 支）')
    parser.add_argument('--skip-existing', action='store_true',
                        help='跳過已下載的股票（斷點續傳）')
    parser.add_argument('--limit', type=int, help='限制處理數量（用於測試）')
    parser.add_argument('--dry-run', action='store_true', help='預覽模式（不寫入）')
    parser.add_argument('--execute', action='store_true', help='執行模式（寫入資料庫）')
    
    args = parser.parse_args()
    
    # 確認執行模式
    dry_run = True
    if args.execute:
        dry_run = False
        print("\n⚠️  執行模式：將寫入資料庫")
        print("=" * 80)
        confirm = input("確定要繼續嗎？(YES/NO): ")
        if confirm != "YES":
            print("已取消")
            return
    
    try:
        downloader = OutstandingSharesDownloader()
        
        if args.stock_id:
            downloader.update_stock(args.stock_id, dry_run)
        elif args.all or args.priority_list:
            downloader.update_all_stocks(
                dry_run=dry_run,
                limit=args.limit,
                priority_list=args.priority_list,
                skip_existing=args.skip_existing
            )
        else:
            parser.print_help()
    
    except ValueError as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n使用者中斷")
        sys.exit(1)


if __name__ == '__main__':
    main()
