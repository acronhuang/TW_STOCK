#!/usr/bin/env python3
"""
P0: 強制精度遷移 - 確保所有數值欄位遷移到 Decimal128

本腳本強制將所有數值欄位轉換為 Decimal128，不論原始類型。

執行方式:
    python3 src/migrations/p0_force_decimal_migration.py --dry-run  # 預覽
    python3 src/migrations/p0_force_decimal_migration.py --execute  # 實際執行
"""

import sys
import argparse
import logging
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 需要遷移的集合和欄位（使用 snake_case 名稱）
MIGRATION_SPECS = {
    "dividend_detail": {
        "decimal_fields": [
            "cash_earnings_distribution",
            "cash_increase_subscription_rate",
            "cash_increase_subscription_price",
            "cash_statutory_surplus",
            "participate_distribution_shares",
            "employee_stock_dividend_ratio",
            "employee_stock_dividend_ratio_total",
            "director_remuneration",
            "stock_earnings_distribution",
            "stock_statutory_surplus",
            "total_employee_cash_dividend",
            "total_employee_stock_dividend",
            "total_employee_stock_dividend_amount",
            "total_cash_capital_increase"
        ],
        "description": "股利政策表 - 強制轉換所有金額欄位為 Decimal128"
    },
    "stock_price": {
        "decimal_fields": [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "adj_close",
            "adjustment_factor"
        ],
        "description": "股價表 - 強制轉換所有價格欄位為 Decimal128"
    }
}


class ForceDecimalMigrator:
    """強制 Decimal128 遷移工具"""
    
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
        log_file = log_dir / f"force_decimal_migration_{timestamp}.log"
        
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
    
    def _force_convert_to_decimal128(self, value):
        """強制將數值轉換為 Decimal128"""
        if value is None or value == '':
            return Decimal128(Decimal('0'))
        
        # 已經是 Decimal128，直接返回
        if isinstance(value, Decimal128):
            return value
        
        try:
            # 強制轉換所有數值類型
            if isinstance(value, (int, float)):
                # 使用字符串轉換避免浮點精度問題
                return Decimal128(Decimal(str(value)))
            elif isinstance(value, str):
                # 嘗試解析字串
                clean_value = value.strip()
                if not clean_value:
                    return Decimal128(Decimal('0'))
                return Decimal128(Decimal(clean_value))
            elif isinstance(value, Decimal):
                return Decimal128(value)
            else:
                self.logger.warning(f"未知類型: {type(value)}, 值: {value}")
                return Decimal128(Decimal('0'))
        except Exception as e:
            self.logger.error(f"轉換失敗: {value} ({type(value)}), 錯誤: {e}")
            return Decimal128(Decimal('0'))
    
    def migrate_collection(self, collection_name: str, decimal_fields: list, 
                          dry_run: bool = True) -> dict:
        """
        強制遷移單一集合
        
        Args:
            collection_name: 集合名稱
            decimal_fields: 需要轉換的欄位列表
            dry_run: 是否為預覽模式
            
        Returns:
            遷移統計
        """
        collection = self.db[collection_name]
        total_docs = collection.count_documents({})
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🔧 強制遷移: {collection_name}")
        self.logger.info(f"總文檔數: {total_docs:,}")
        self.logger.info(f"轉換欄位: {', '.join(decimal_fields)}")
        self.logger.info(f"模式: {'預覽' if dry_run else '實際執行（強制）'}")
        self.logger.info(f"{'='*80}\n")
        
        stats = {
            'total': total_docs,
            'processed': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0
        }
        
        if total_docs == 0:
            self.logger.warning(f"⚠️  集合 {collection_name} 沒有文檔，跳過")
            return stats
        
        # 批次處理
        batch_size = 500
        cursor = collection.find({}).batch_size(batch_size)
        
        for doc in cursor:
            stats['processed'] += 1
            update_fields = {}
            
            # 強制轉換每個欄位
            for field in decimal_fields:
                if field in doc:
                    value = doc[field]
                    converted = self._force_convert_to_decimal128(value)
                    
                    # 只要不是 Decimal128，就強制更新
                    if not isinstance(value, Decimal128):
                        update_fields[field] = converted
            
            # 執行更新
            if update_fields:
                if not dry_run:
                    try:
                        collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": update_fields}
                        )
                        stats['updated'] += 1
                    except Exception as e:
                        self.logger.error(f"更新失敗 (_id: {doc['_id']}): {e}")
                        stats['errors'] += 1
                else:
                    stats['updated'] += 1
            else:
                stats['skipped'] += 1
            
            # 進度報告
            if stats['processed'] % 5000 == 0:
                progress = stats['processed'] / total_docs * 100
                self.logger.info(
                    f"進度: {stats['processed']:,}/{total_docs:,} ({progress:.1f}%) | "
                    f"更新: {stats['updated']:,} | 跳過: {stats['skipped']:,}"
                )
        
        self.logger.info(f"\n✅ 遷移完成: {collection_name}")
        self.logger.info(f"   處理: {stats['processed']:,}")
        self.logger.info(f"   更新: {stats['updated']:,}")
        self.logger.info(f"   跳過: {stats['skipped']:,}")
        self.logger.info(f"   錯誤: {stats['errors']:,}\n")
        
        return stats
    
    def migrate_all(self, dry_run: bool = True):
        """執行所有遷移"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 開始 P0 階段：強制 Decimal128 精度遷移")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式（不會實際修改數據）' if dry_run else '實際執行模式（強制轉換）'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        all_stats = []
        
        for collection_name, spec in MIGRATION_SPECS.items():
            self.logger.info(f"📊 {spec['description']}")
            
            # 檢查集合是否存在
            if collection_name not in self.db.list_collection_names():
                self.logger.warning(f"⚠️  集合不存在: {collection_name}，跳過")
                continue
            
            stats = self.migrate_collection(
                collection_name,
                spec['decimal_fields'],
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
        self.logger.info("📊 遷移總結報告")
        self.logger.info("="*80)
        self.logger.info(f"集合數量: {len(all_stats)}")
        self.logger.info(f"總處理: {total_processed:,} 筆")
        self.logger.info(f"總更新: {total_updated:,} 筆")
        self.logger.info(f"總錯誤: {total_errors:,} 筆")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式，尚未實際修改數據")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 強制遷移已完成！所有數值欄位已轉換為 Decimal128")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P0: 強制 Decimal128 精度遷移"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='預覽模式（不實際修改數據）'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='實際執行遷移'
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
        print("\n使用 --dry-run 先預覽")
        sys.exit(1)
    
    if args.execute:
        print("\n⚠️  警告: 您即將強制修改資料庫數據！")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行遷移
    migrator = ForceDecimalMigrator(args.mongo_uri, args.db_name)
    migrator.migrate_all(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
