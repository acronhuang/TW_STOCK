#!/usr/bin/env python3
"""
P2: 關鍵欄位補齊工具

補齊以下欄位：
1. taiwan_stock_info: security_type, industry_l1, industry_l2, is_delisted
2. stock_price: ex_dividend_reference_price, limit_up, limit_down
3. dividend_detail: tax_credit_rate, payment_date

執行方式:
    python3 src/migrations/p2_field_enrichment.py --task add-security-type --dry-run
    python3 src/migrations/p2_field_enrichment.py --task all --execute
"""

import sys
import argparse
import logging
import re
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient

# 設定路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class FieldEnrichment:
    """欄位補齊工具"""
    
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
        log_file = log_dir / f"field_enrichment_{timestamp}.log"
        
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
    
    def classify_security_type(self, stock_id: str, stock_name: str = "") -> str:
        """
        根據股票代碼和名稱判斷證券類型
        
        Returns:
            'Stock', 'ETF', 'Warrant', 'ETN', 'DR' 等
        """
        # ETF: 00XX 開頭（6-7 碼）
        if re.match(r'^00\d{2,3}[A-Z]?$', stock_id):
            return 'ETF'
        
        # 權證: 6 碼以上且包含特定字母
        if len(stock_id) > 6:
            return 'Warrant'
        
        # 特別股: 股票名稱包含「特」
        if '特' in stock_name:
            return 'PreferredStock'
        
        # KY 股: 股票名稱包含 KY
        if 'KY' in stock_name:
            return 'KY-Stock'
        
        # 預設為普通股
        return 'Stock'
    
    def add_security_type(self, dry_run: bool = True) -> dict:
        """
        為 taiwan_stock_info 新增 security_type 欄位
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info("任務: 新增 security_type 欄位")
        self.logger.info(f"{'='*80}\n")
        
        collection = self.db.taiwan_stock_info
        
        # 找出沒有 security_type 的文檔
        total = collection.count_documents({"security_type": {"$exists": False}})
        self.logger.info(f"需要更新的股票數: {total:,}")
        
        if total == 0:
            self.logger.info("✅ 所有股票已有 security_type 欄位\n")
            return {'total': 0, 'updated': 0}
        
        stats = {'total': total, 'updated': 0, 'errors': 0}
        
        stocks = collection.find({"security_type": {"$exists": False}})
        
        for stock in stocks:
            stock_id = stock.get('stock_id', '')
            stock_name = stock.get('stock_name', '')
            
            security_type = self.classify_security_type(stock_id, stock_name)
            
            if not dry_run:
                try:
                    collection.update_one(
                        {"_id": stock["_id"]},
                        {"$set": {"security_type": security_type}}
                    )
                    stats['updated'] += 1
                except Exception as e:
                    self.logger.error(f"更新失敗 ({stock_id}): {e}")
                    stats['errors'] += 1
            else:
                stats['updated'] += 1
                if stats['updated'] <= 10:  # 顯示前 10 個範例
                    self.logger.info(f"  {stock_id} ({stock_name}) → {security_type}")
        
        self.logger.info(f"\n✅ 完成")
        self.logger.info(f"   {'將新增' if dry_run else '已新增'}: {stats['updated']:,} 筆\n")
        
        return stats
    
    def split_industry_category(self, dry_run: bool = True) -> dict:
        """
        將 industry_category 拆分為 industry_l1 和 industry_l2
        例如: "半導體業" → industry_l1="電子工業", industry_l2="半導體業"
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info("任務: 拆分行業分類為多級")
        self.logger.info(f"{'='*80}\n")
        
        collection = self.db.taiwan_stock_info
        
        # 台灣股市行業分類映射（簡化版）
        industry_mapping = {
            "水泥工業": ("建材營造", "水泥工業"),
            "食品工業": ("民生工業", "食品工業"),
            "塑膠工業": ("塑膠工業", "塑膠工業"),
            "紡織纖維": ("民生工業", "紡織纖維"),
            "電機機械": ("電機機械", "電機機械"),
            "電器電纜": ("電機機械", "電器電纜"),
            "化學生技醫療": ("生技醫療", "化學生技醫療"),
            "化學工業": ("化學工業", "化學工業"),
            "生技醫療業": ("生技醫療", "生技醫療業"),
            "玻璃陶瓷": ("建材營造", "玻璃陶瓷"),
            "造紙工業": ("民生工業", "造紙工業"),
            "鋼鐵工業": ("鋼鐵工業", "鋼鐵工業"),
            "橡膠工業": ("橡膠工業", "橡膠工業"),
            "汽車工業": ("汽車工業", "汽車工業"),
            "半導體業": ("電子工業", "半導體業"),
            "電腦及週邊設備業": ("電子工業", "電腦及週邊設備業"),
            "光電業": ("電子工業", "光電業"),
            "通信網路業": ("電子工業", "通信網路業"),
            "電子零組件業": ("電子工業", "電子零組件業"),
            "電子通路業": ("電子工業", "電子通路業"),
            "資訊服務業": ("電子工業", "資訊服務業"),
            "其他電子業": ("電子工業", "其他電子業"),
            "建材營造業": ("建材營造", "建材營造業"),
            "航運業": ("航運業", "航運業"),
            "觀光事業": ("觀光事業", "觀光事業"),
            "金融保險業": ("金融保險", "金融保險業"),
            "貿易百貨業": ("綜合", "貿易百貨業"),
            "油電燃氣業": ("油電燃氣", "油電燃氣業"),
            "綜合": ("綜合", "綜合"),
            "其他": ("其他", "其他"),
        }
        
        total = collection.count_documents({"industry_l1": {"$exists": False}})
        self.logger.info(f"需要更新的股票數: {total:,}")
        
        if total == 0:
            self.logger.info("✅ 所有股票已有多級行業分類\n")
            return {'total': 0, 'updated': 0}
        
        stats = {'total': total, 'updated': 0, 'errors': 0}
        
        stocks = collection.find({"industry_l1": {"$exists": False}})
        
        for stock in stocks:
            industry = stock.get('industry_category', '其他')
            
            # 查找映射
            l1, l2 = industry_mapping.get(industry, ("其他", industry))
            
            if not dry_run:
                try:
                    collection.update_one(
                        {"_id": stock["_id"]},
                        {"$set": {
                            "industry_l1": l1,
                            "industry_l2": l2
                        }}
                    )
                    stats['updated'] += 1
                except Exception as e:
                    self.logger.error(f"更新失敗: {e}")
                    stats['errors'] += 1
            else:
                stats['updated'] += 1
                if stats['updated'] <= 10:
                    self.logger.info(f"  {stock.get('stock_id')} | {industry} → L1:{l1}, L2:{l2}")
        
        self.logger.info(f"\n✅ 完成")
        self.logger.info(f"   {'將新增' if dry_run else '已新增'}: {stats['updated']:,} 筆\n")
        
        return stats
    
    def mark_delisted_stocks(self, dry_run: bool = True) -> dict:
        """
        根據 delisting 表標記已下市的股票
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info("任務: 標記已下市股票")
        self.logger.info(f"{'='*80}\n")
        
        # 獲取下市清單
        delisted_ids = list(self.db.delisting.distinct('stock_id'))
        self.logger.info(f"下市股票數: {len(delisted_ids)}")
        
        if not delisted_ids:
            self.logger.info("⚠️  找不到下市資料\n")
            return {'total': 0, 'updated': 0}
        
        stats = {'total': len(delisted_ids), 'updated': 0, 'errors': 0}
        
        collection = self.db.taiwan_stock_info
        
        for stock_id in delisted_ids:
            if not dry_run:
                try:
                    # 從 delisting 表獲取下市日期
                    delisting_info = self.db.delisting.find_one({"stock_id": stock_id})
                    delisting_date = delisting_info.get('date') if delisting_info else None
                    
                    result = collection.update_one(
                        {"stock_id": stock_id},
                        {"$set": {
                            "is_delisted": True,
                            "delisting_date": delisting_date
                        }}
                    )
                    
                    if result.modified_count > 0:
                        stats['updated'] += 1
                except Exception as e:
                    self.logger.error(f"更新失敗 ({stock_id}): {e}")
                    stats['errors'] += 1
            else:
                stats['updated'] += 1
                if stats['updated'] <= 10:
                    self.logger.info(f"  {stock_id} → is_delisted=True")
        
        self.logger.info(f"\n✅ 完成")
        self.logger.info(f"   {'將標記' if dry_run else '已標記'}: {stats['updated']:,} 筆\n")
        
        return stats
    
    def run_all_tasks(self, dry_run: bool = True):
        """執行所有補齊任務"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 開始 P2 階段：關鍵欄位補齊")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行模式'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        all_stats = {}
        
        # 任務 1: 新增證券類型
        all_stats['security_type'] = self.add_security_type(dry_run)
        
        # 任務 2: 拆分行業分類
        all_stats['industry_split'] = self.split_industry_category(dry_run)
        
        # 任務 3: 標記下市股票
        all_stats['delisting_mark'] = self.mark_delisted_stocks(dry_run)
        
        # 總結
        self._print_summary(all_stats, dry_run)
    
    def _print_summary(self, all_stats: dict, dry_run: bool):
        """列印總結報告"""
        total_updated = sum(s['updated'] for s in all_stats.values())
        
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 補齊總結報告")
        self.logger.info("="*80)
        self.logger.info(f"任務數量: {len(all_stats)}")
        self.logger.info(f"總更新: {total_updated:,} 筆")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式，尚未實際修改數據")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 補齊已完成！關鍵欄位已新增")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P2: 關鍵欄位補齊"
    )
    
    parser.add_argument(
        '--task',
        choices=['add-security-type', 'split-industry', 'mark-delisted', 'all'],
        default='all',
        help='選擇執行的任務'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='預覽模式（不實際修改數據）'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='實際執行'
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
        print("\n⚠️  警告: 您即將新增欄位到資料庫！")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行任務
    enrichment = FieldEnrichment(args.mongo_uri, args.db_name)
    
    if args.task == 'all':
        enrichment.run_all_tasks(dry_run=args.dry_run)
    elif args.task == 'add-security-type':
        enrichment.add_security_type(dry_run=args.dry_run)
    elif args.task == 'split-industry':
        enrichment.split_industry_category(dry_run=args.dry_run)
    elif args.task == 'mark-delisted':
        enrichment.mark_delisted_stocks(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
