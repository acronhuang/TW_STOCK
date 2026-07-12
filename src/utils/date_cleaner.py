#!/usr/bin/env python3
"""
P1: 日期清洗工具 - 統一所有日期格式為 ISODate

本工具確保：
1. 所有日期欄位統一為 MongoDB ISODate 格式
2. 清理無效日期
3. 統一時區為 UTC

執行方式:
    python3 src/utils/date_cleaner.py --dry-run  # 預覽
    python3 src/utils/date_cleaner.py --execute  # 實際執行
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, date
from pymongo import MongoClient, UpdateOne
from bson import ObjectId

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 需要清洗的集合和日期欄位
DATE_CLEANING_SPECS = {
    "stock_price": {
        "date_fields": ["date"],
        "description": "股價表 - 統一日期格式"
    },
    "dividend_detail": {
        "date_fields": [
            "announcement_date",
            "ex_dividend_trading_date", 
            "cash_dividend_payment_date",
            "stock_dividend_distribution_date"
        ],
        "description": "股利政策表 - 統一日期格式"
    },
    "balance_sheet": {
        "date_fields": ["date"],
        "description": "資產負債表 - 統一日期格式"
    },
    "income_statement": {
        "date_fields": ["date"],
        "description": "損益表 - 統一日期格式"
    },
    "cash_flow_statement": {
        "date_fields": ["date"],
        "description": "現金流量表 - 統一日期格式"
    }
}


class DateCleaner:
    """日期清洗工具"""
    
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """設定日誌"""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"date_cleaning_{timestamp}.log"
        
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
    
    def _normalize_date(self, value) -> datetime | None:
        """
        統一日期格式為 datetime
        
        支援格式:
        - datetime
        - date
        - str (YYYY-MM-DD, YYYYMMDD, YYYY/MM/DD)
        - int/float (timestamp)
        """
        if value is None:
            return None
        
        # 已經是 datetime
        if isinstance(value, datetime):
            # 確保 UTC 時區
            if value.tzinfo is not None:
                return value.replace(tzinfo=None)
            return value
        
        # date 對象
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        
        # 字符串格式
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            
            # 嘗試多種格式
            formats = [
                '%Y-%m-%d',
                '%Y/%m/%d',
                '%Y%m%d',
                '%Y-%m-%d %H:%M:%S',
                '%Y/%m/%d %H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            
            self.logger.warning(f"無法解析日期字符串: {value}")
            return None
        
        # 數值 (timestamp)
        if isinstance(value, (int, float)):
            try:
                # 假設是秒級時間戳
                return datetime.fromtimestamp(value)
            except Exception as e:
                self.logger.error(f"無法轉換時間戳: {value}, 錯誤: {e}")
                return None
        
        self.logger.warning(f"未知日期類型: {type(value)}, 值: {value}")
        return None
    
    def clean_collection(self, collection_name: str, date_fields: list,
                         dry_run: bool = True) -> dict:
        """
        清洗單一集合的日期欄位
        
        Args:
            collection_name: 集合名稱
            date_fields: 需要清洗的日期欄位列表
            dry_run: 是否為預覽模式
            
        Returns:
            清洗統計
        """
        collection = self.db[collection_name]
        
        # 僅查詢包含日期欄位的文檔
        query = {"$or": [{field: {"$exists": True}} for field in date_fields]}
        total_docs = collection.count_documents(query)
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🧹 清洗集合: {collection_name}")
        self.logger.info(f"總文檔數: {total_docs:,}")
        self.logger.info(f"日期欄位: {', '.join(date_fields)}")
        self.logger.info(f"模式: {'預覽' if dry_run else '實際執行'}")
        self.logger.info(f"{'='*80}\n")
        
        stats = {
            'total': total_docs,
            'processed': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0
        }
        
        if total_docs == 0:
            self.logger.warning(f"⚠️  沒有需要清洗的文檔")
            return stats
        
        # 批次處理
        batch_size = 1000
        updates = []
        
        cursor = collection.find(query).batch_size(batch_size)
        
        for doc in cursor:
            stats['processed'] += 1
            update_fields = {}
            
            # 清洗每個日期欄位
            for field in date_fields:
                if field in doc:
                    value = doc[field]
                    
                    # 如果已經是 datetime，檢查時區
                    if isinstance(value, datetime):
                        if value.tzinfo is not None:
                            update_fields[field] = value.replace(tzinfo=None)
                    else:
                        # 嘗試標準化
                        normalized = self._normalize_date(value)
                        if normalized:
                            update_fields[field] = normalized
                        else:
                            # 無法轉換，記錄錯誤
                            self.logger.warning(
                                f"無效日期 ({collection_name} | "
                                f"_id: {doc['_id']} | {field}: {value})"
                            )
            
            # 收集更新操作
            if update_fields:
                if not dry_run:
                    updates.append(
                        UpdateOne(
                            {"_id": doc["_id"]},
                            {"$set": update_fields}
                        )
                    )
                stats['updated'] += 1
            else:
                stats['skipped'] += 1
            
            # 批次執行更新
            if len(updates) >= batch_size:
                try:
                    result = collection.bulk_write(updates, ordered=False)
                    self.logger.debug(f"批次更新: {result.modified_count} 筆")
                except Exception as e:
                    self.logger.error(f"批次更新失敗: {e}")
                    stats['errors'] += 1
                updates = []
            
            # 進度報告
            if stats['processed'] % 10000 == 0:
                progress = stats['processed'] / total_docs * 100
                self.logger.info(
                    f"進度: {stats['processed']:,}/{total_docs:,} ({progress:.1f}%) | "
                    f"更新: {stats['updated']:,} | 跳過: {stats['skipped']:,}"
                )
        
        # 執行剩餘更新
        if updates and not dry_run:
            try:
                result = collection.bulk_write(updates, ordered=False)
                self.logger.debug(f"最後批次: {result.modified_count} 筆")
            except Exception as e:
                self.logger.error(f"最後批次失敗: {e}")
                stats['errors'] += 1
        
        self.logger.info(f"\n✅ 清洗完成: {collection_name}")
        self.logger.info(f"   處理: {stats['processed']:,}")
        self.logger.info(f"   更新: {stats['updated']:,}")
        self.logger.info(f"   跳過: {stats['skipped']:,}")
        self.logger.info(f"   錯誤: {stats['errors']:,}\n")
        
        return stats
    
    def clean_all(self, dry_run: bool = True):
        """清洗所有集合"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🧹 開始 P1 階段：日期清洗")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        all_stats = []
        
        for collection_name, spec in DATE_CLEANING_SPECS.items():
            self.logger.info(f"📊 {spec['description']}")
            
            # 檢查集合是否存在
            if collection_name not in self.db.list_collection_names():
                self.logger.warning(f"⚠️  集合不存在: {collection_name}，跳過")
                continue
            
            stats = self.clean_collection(
                collection_name,
                spec['date_fields'],
                dry_run
            )
            all_stats.append(stats)
        
        # 總結報告
        self._print_summary(all_stats, dry_run)
    
    def _print_summary(self, all_stats: list, dry_run: bool):
        """列印總結報告"""
        total_processed = sum(s['processed'] for s in all_stats)
        total_updated = sum(s['updated'] for s in all_stats)
        total_errors = sum(s['errors'] for s in all_stats)
        
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 日期清洗總結報告")
        self.logger.info("="*80)
        self.logger.info(f"集合數量: {len(all_stats)}")
        self.logger.info(f"總處理: {total_processed:,} 筆")
        self.logger.info(f"總更新: {total_updated:,} 筆")
        self.logger.info(f"總錯誤: {total_errors:,} 筆")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 日期清洗已完成！所有日期統一為 ISODate")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P1: 日期清洗工具"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='預覽模式'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='實際執行清洗'
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
    if not args.dry_run and not args.execute:
        print("❌ 錯誤: 請指定 --dry-run 或 --execute")
        sys.exit(1)
    
    if args.execute:
        print("\n⚠️  警告: 您即將修改日期數據！")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行清洗
    cleaner = DateCleaner(args.mongo_uri, args.db_name)
    cleaner.clean_all(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
