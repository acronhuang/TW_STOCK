#!/usr/bin/env python3
"""
P1: 全域命名規範遷移 - 統一所有欄位命名為 snake_case

執行方式:
    python3 src/migrations/p1_naming_migration.py --dry-run  # 預覽
    python3 src/migrations/p1_naming_migration.py --execute  # 實際執行
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient

# 設定路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 欄位重命名規範
FIELD_RENAME_SPECS = {
    "stock_price": {
        "renames": {
            "closePrice": "close",
            "tradeVolume": "volume",
            "latestCumulativeAdjustmentFactor": "adjustment_factor"
        },
        "description": "股價資料表 - 統一為 snake_case"
    },
    "dividend_detail": {
        "renames": {
            "AnnouncementDate": "announcement_date",
            "AnnouncementTime": "announcement_time",
            "CashDividendPaymentDate": "cash_dividend_payment_date",
            "CashEarningsDistribution": "cash_earnings_distribution",
            "CashExDividendTradingDate": "cash_ex_dividend_date",
            "CashIncreaseSubscriptionRate": "cash_increase_subscription_rate",
            "CashIncreaseSubscriptionpRrice": "cash_increase_subscription_price",
            "CashStatutorySurplus": "cash_statutory_surplus",
            "ParticipateDistributionOfTotalShares": "participate_distribution_shares",
            "RatioOfEmployeeStockDividend": "employee_stock_dividend_ratio",
            "RatioOfEmployeeStockDividendOfTotal": "employee_stock_dividend_ratio_total",
            "RemunerationOfDirectorsAndSupervisors": "director_remuneration",
            "StockEarningsDistribution": "stock_earnings_distribution",
            "StockExDividendTradingDate": "stock_ex_dividend_date",
            "StockStatutorySurplus": "stock_statutory_surplus",
            "TotalEmployeeCashDividend": "total_employee_cash_dividend",
            "TotalEmployeeStockDividend": "total_employee_stock_dividend",
            "TotalEmployeeStockDividendAmount": "total_employee_stock_dividend_amount",
            "TotalNumberOfCashCapitalIncrease": "total_cash_capital_increase"
        },
        "description": "股利政策表 - 統一為 snake_case"
    },
    "taiwan_stock_per": {
        "renames": {
            "PER": "pe_ratio",
            "PBR": "pb_ratio"
        },
        "description": "本益比表 - 統一術語"
    }
}


class NamingMigrator:
    """命名規範遷移工具"""
    
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
        log_file = log_dir / f"naming_migration_{timestamp}.log"
        
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
    
    def migrate_collection(self, collection_name: str, renames: dict,
                          dry_run: bool = True) -> dict:
        """
        遷移單一集合的欄位名稱
        
        Args:
            collection_name: 集合名稱
            renames: 欄位重命名映射 {舊名: 新名}
            dry_run: 是否為預覽模式
            
        Returns:
            遷移統計
        """
        collection = self.db[collection_name]
        
        # 只統計需要重命名的文檔
        query = {"$or": [{old_name: {"$exists": True}} for old_name in renames.keys()]}
        total_docs = collection.count_documents(query)
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"開始遷移: {collection_name}")
        self.logger.info(f"需要更新的文檔數: {total_docs:,}")
        self.logger.info(f"欄位映射:")
        for old, new in renames.items():
            self.logger.info(f"  {old} → {new}")
        self.logger.info(f"模式: {'預覽' if dry_run else '實際執行'}")
        self.logger.info(f"{'='*80}\n")
        
        stats = {
            'total': total_docs,
            'processed': 0,
            'updated': 0,
            'errors': 0
        }
        
        if total_docs == 0:
            self.logger.info("✅ 無需更新，所有欄位名稱已為最新\n")
            return stats
        
        # 使用 MongoDB 的 $rename 操作（批次操作）
        if not dry_run:
            try:
                # 構建 rename 操作
                rename_op = {}
                for old_name, new_name in renames.items():
                    rename_op[old_name] = new_name
                
                # 執行批次重命名
                result = collection.update_many(
                    query,
                    {"$rename": rename_op}
                )
                
                stats['updated'] = result.modified_count
                self.logger.info(f"✅ 成功更新 {stats['updated']:,} 筆文檔")
                
            except Exception as e:
                self.logger.error(f"❌ 批次更新失敗: {e}")
                stats['errors'] = total_docs
        else:
            stats['updated'] = total_docs
            self.logger.info(f"✅ 預覽: 將更新 {stats['updated']:,} 筆文檔")
        
        stats['processed'] = total_docs
        
        return stats
    
    def migrate_all(self, dry_run: bool = True) -> dict:
        """遷移所有集合"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 開始 P1 階段：全域命名規範遷移")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式（不會實際修改數據）' if dry_run else '實際執行模式'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        all_stats = {}
        
        for collection_name, spec in FIELD_RENAME_SPECS.items():
            # 檢查集合是否存在
            if collection_name not in self.db.list_collection_names():
                self.logger.warning(f"⚠️  集合不存在: {collection_name}，跳過")
                continue
            
            self.logger.info(f"📊 {spec['description']}")
            stats = self.migrate_collection(
                collection_name,
                spec['renames'],
                dry_run
            )
            all_stats[collection_name] = stats
        
        # 總結報告
        self._print_summary(all_stats, dry_run)
        
        return all_stats
    
    def _print_summary(self, all_stats: dict, dry_run: bool):
        """列印總結報告"""
        total_updated = sum(s['updated'] for s in all_stats.values())
        total_errors = sum(s['errors'] for s in all_stats.values())
        
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 遷移總結報告")
        self.logger.info("="*80)
        self.logger.info(f"集合數量: {len(all_stats)}")
        self.logger.info(f"總更新: {total_updated:,} 筆")
        self.logger.info(f"總錯誤: {total_errors:,} 筆")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式，尚未實際修改數據")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 遷移已完成！所有欄位已統一為 snake_case 命名")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P1: 全域命名規範遷移"
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
        print("\n使用 --dry-run 先預覽影響範圍")
        sys.exit(1)
    
    if args.execute:
        print("\n⚠️  警告: 您即將實際修改資料庫欄位名稱！")
        print("這會影響現有的查詢程式碼，請確保已做好備份。")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行遷移
    migrator = NamingMigrator(args.mongo_uri, args.db_name)
    migrator.migrate_all(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
