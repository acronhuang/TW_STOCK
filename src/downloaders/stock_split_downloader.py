#!/usr/bin/env python3
"""
P2: 股票分割數據下載器

下載並整合台灣股票分割/減資歷史:
1. 股票分割 (Stock Split)
2. 資本減少 (Capital Reduction)

數據來源: FinMind TaiwanStockCapitalReduction API

儲存欄位:
- stock_id: 股票代碼
- date: 分割/減資日期
- type: 'split' 或 'reduction'
- old_shares: 原股數
- new_shares: 新股數
- ratio: 比例 (new_shares / old_shares)
- reason: 原因說明

執行方式:
    python3 src/downloaders/stock_split_downloader.py --stock-id 2330 --dry-run
    python3 src/downloaders/stock_split_downloader.py --all --execute
"""

import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128
import requests

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class StockSplitDownloader:
    """股票分割數據下載器"""
    
    def __init__(self, 
                 api_token: str = None,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        
        # FinMind API Token
        self.api_token = api_token or os.getenv('FINMIND_API_TOKEN')
        if not self.api_token:
            raise ValueError("請設定 FINMIND_API_TOKEN 環境變數或傳入 api_token 參數")
        
        self.base_url = "https://api.finmindtrade.com/api/v4/data"
        
        # MongoDB
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.logger = self._setup_logger()
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.6  # 每秒最多請求1.5次
    
    def _setup_logger(self) -> logging.Logger:
        """設定日誌"""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"stock_split_{timestamp}.log"
        
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
    
    def _api_request(self, dataset: str, stock_id: str, start_date: str = "2000-01-01") -> dict:
        """
        發送 API 請求
        
        Args:
            dataset: API 資料集名稱
            stock_id: 股票代碼
            start_date: 起始日期
            
        Returns:
            API 回應
        """
        self._rate_limit()
        
        params = {
            'dataset': dataset,
            'data_id': stock_id,
            'start_date': start_date,
            'token': self.api_token
        }
        
        try:
            self.logger.debug(f"API 請求: {dataset}, 股票: {stock_id}")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 200:
                self.logger.error(f"API 錯誤: {data.get('msg')}")
                return None
            
            return data.get('data', [])
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API 請求失敗: {e}")
            return None
    
    def download_capital_reduction(self, stock_id: str) -> list:
        """
        下載資本減少數據
        
        Returns:
            [{date, old_shares, new_shares, ratio, reason}, ...]
        """
        data = self._api_request('TaiwanStockCapitalReduction', stock_id)
        
        if not data:
            return []
        
        events = []
        
        for item in data:
            try:
                date_str = item.get('date')
                if not date_str:
                    continue
                
                # 解析日期
                date = datetime.strptime(date_str, '%Y-%m-%d')
                
                # 減資比例 (ex: 0.8 表示減資20%)
                reduction_ratio = float(item.get('CapitalReductionRatio', 1.0))
                
                # 原因
                reason = item.get('CapitalReductionReason', '')
                
                if reduction_ratio < 1.0:  # 確實有減資
                    events.append({
                        'date': date,
                        'type': 'capital_reduction',
                        'old_shares': 1.0,
                        'new_shares': reduction_ratio,
                        'ratio': reduction_ratio,
                        'reason': reason
                    })
                    
                    self.logger.debug(
                        f"{date_str}: 減資 {(1-reduction_ratio)*100:.2f}%, "
                        f"比例 {reduction_ratio:.4f}"
                    )
            
            except Exception as e:
                self.logger.warning(f"解析減資數據失敗: {item}, 錯誤: {e}")
                continue
        
        return events
    
    def save_split_events(self, stock_id: str, events: list, dry_run: bool = True) -> dict:
        """
        儲存股票分割事件到資料庫
        
        Args:
            stock_id: 股票代碼
            events: 分割事件列表
            dry_run: 是否為預覽模式
            
        Returns:
            統計資訊
        """
        stats = {
            'stock_id': stock_id,
            'total_events': len(events),
            'inserted': 0,
            'updated': 0,
            'errors': 0
        }
        
        if not events:
            return stats
        
        if dry_run:
            self.logger.info(f"預覽: 將儲存 {len(events)} 個分割事件")
            stats['inserted'] = len(events)
            return stats
        
        # 準備更新操作
        updates = []
        
        for event in events:
            updates.append(
                UpdateOne(
                    {
                        'stock_id': stock_id,
                        'date': event['date']
                    },
                    {
                        '$set': {
                            'stock_id': stock_id,
                            'date': event['date'],
                            'type': event['type'],
                            'old_shares': Decimal128(Decimal(str(event['old_shares']))),
                            'new_shares': Decimal128(Decimal(str(event['new_shares']))),
                            'ratio': Decimal128(Decimal(str(event['ratio']))),
                            'reason': event.get('reason', ''),
                            'updated_at': datetime.now()
                        }
                    },
                    upsert=True
                )
            )
        
        try:
            result = self.db.stock_split_events.bulk_write(updates, ordered=False)
            stats['inserted'] = result.upserted_count
            stats['updated'] = result.modified_count
            
            self.logger.info(
                f"✅ 儲存成功: 新增 {stats['inserted']}, "
                f"更新 {stats['updated']}"
            )
            
        except Exception as e:
            self.logger.error(f"❌ 儲存失敗: {e}")
            stats['errors'] = 1
        
        return stats
    
    def download_stock(self, stock_id: str, dry_run: bool = True) -> dict:
        """下載單一股票的分割數據"""
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"下載 {stock_id} 股票分割數據")
        self.logger.info(f"{'='*80}")
        
        # 下載減資數據
        events = self.download_capital_reduction(stock_id)
        
        self.logger.info(f"找到 {len(events)} 個分割/減資事件")
        
        # 顯示詳細資訊
        if events:
            for event in events:
                self.logger.info(
                    f"  {event['date'].strftime('%Y-%m-%d')}: "
                    f"{event['type']} | 比例 {event['ratio']:.4f} | "
                    f"{event.get('reason', '')}"
                )
        
        # 儲存到資料庫
        stats = self.save_split_events(stock_id, events, dry_run)
        
        self.logger.info(f"\n結果: {stats}")
        self.logger.info(f"{'='*80}\n")
        
        return stats
    
    def download_all(self, dry_run: bool = True, limit: int = None) -> dict:
        """下載所有股票的分割數據"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 股票分割數據下載器")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行模式'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        # 獲取所有股票
        stock_ids = self.db.stock_price.distinct('symbol')
        
        if limit:
            stock_ids = stock_ids[:limit]
        
        self.logger.info(f"股票總數: {len(stock_ids)}\n")
        
        # 統計
        summary = {
            'total_stocks': len(stock_ids),
            'success': 0,
            'errors': 0,
            'total_events': 0,
            'total_inserted': 0
        }
        
        for i, stock_id in enumerate(stock_ids, 1):
            self.logger.info(f"[{i}/{len(stock_ids)}] {stock_id}")
            
            stats = self.download_stock(stock_id, dry_run)
            
            summary['total_events'] += stats['total_events']
            summary['total_inserted'] += stats['inserted']
            
            if stats['errors'] == 0:
                summary['success'] += 1
            else:
                summary['errors'] += 1
        
        # 總結報告
        self._print_summary(summary, dry_run)
        
        return summary
    
    def _print_summary(self, summary: dict, dry_run: bool):
        """列印總結報告"""
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 下載總結")
        self.logger.info("="*80)
        self.logger.info(f"股票總數: {summary['total_stocks']:,}")
        self.logger.info(f"  成功: {summary['success']:,}")
        self.logger.info(f"  失敗: {summary['errors']:,}")
        self.logger.info(f"\n分割事件: {summary['total_events']:,} 個")
        self.logger.info(f"{'將儲存' if dry_run else '已儲存'}: {summary['total_inserted']:,} 個")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式")
        else:
            self.logger.info("\n✅ 股票分割數據下載完成！")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P2: 股票分割數據下載器"
    )
    
    parser.add_argument('--stock-id', help='指定股票代碼')
    parser.add_argument('--all', action='store_true', help='下載所有股票')
    parser.add_argument('--limit', type=int, help='限制股票數量')
    parser.add_argument('--dry-run', action='store_true', help='預覽模式')
    parser.add_argument('--execute', action='store_true', help='實際執行')
    parser.add_argument('--api-token', help='FinMind API Token')
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017/')
    parser.add_argument('--db-name', default='tw_stock_analysis')
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("❌ 請指定 --dry-run 或 --execute")
        sys.exit(1)
    
    if not args.stock_id and not args.all:
        print("❌ 請指定 --stock-id 或 --all")
        sys.exit(1)
    
    if args.execute:
        response = input("⚠️  確認執行？請輸入 'YES': ")
        if response != 'YES':
            sys.exit(0)
    
    try:
        downloader = StockSplitDownloader(
            api_token=args.api_token,
            mongo_uri=args.mongo_uri,
            db_name=args.db_name
        )
        
        if args.stock_id:
            downloader.download_stock(args.stock_id, dry_run=args.dry_run)
        else:
            downloader.download_all(dry_run=args.dry_run, limit=args.limit)
    
    except ValueError as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
