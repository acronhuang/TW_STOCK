#!/usr/bin/env python3
"""
資料庫 Schema 遷移：Float → Decimal128
將所有金額、價格欄位從 Float 轉換為 Decimal128 以確保精度
"""

from pymongo import MongoClient
from decimal import Decimal, InvalidOperation
from bson.decimal128 import Decimal128
from datetime import datetime
import logging

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/schema_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SchemaDecimalMigrator:
    """Schema 遷移器：Float → Decimal128"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.stats = {
            'total_processed': 0,
            'total_updated': 0,
            'errors': 0,
            'collections': {}
        }
        
    def safe_to_decimal128(self, value) -> Decimal128:
        """安全轉換為 Decimal128"""
        if value is None or value == '':
            return Decimal128('0')
        
        try:
            # 如果已經是 Decimal128，直接返回
            if isinstance(value, Decimal128):
                return value
            
            # 轉換為字串再創建 Decimal
            decimal_value = Decimal(str(value))
            return Decimal128(decimal_value)
        except (InvalidOperation, ValueError, TypeError) as e:
            logger.warning(f"無法轉換值 {value}: {e}")
            return Decimal128('0')
    
    def migrate_tickers(self):
        """遷移 tickers 集合（個股行情）"""
        logger.info("=" * 60)
        logger.info("開始遷移 tickers 集合")
        logger.info("=" * 60)
        
        collection = self.db.tickers
        total = collection.count_documents({})
        logger.info(f"總筆數: {total:,}")
        
        # 需要轉換的欄位
        price_fields = ['openPrice', 'highPrice', 'lowPrice', 'closePrice', 'close']
        numeric_fields = ['change', 'changePercent', 'tradeVolume', 'volume', 
                         'tradeValue', 'transaction', 'tradeWeight']
        institutional_fields = ['finiNetBuySell', 'sitcNetBuySell', 'dealersNetBuySell']
        
        all_fields = price_fields + numeric_fields + institutional_fields
        
        processed = 0
        updated = 0
        batch_size = 1000
        
        cursor = collection.find().batch_size(batch_size)
        
        for doc in cursor:
            processed += 1
            
            updates = {}
            needs_update = False
            
            # 轉換所有數值欄位
            for field in all_fields:
                if field in doc:
                    old_value = doc[field]
                    
                    # 檢查是否需要轉換（非 Decimal128）
                    if not isinstance(old_value, Decimal128):
                        new_value = self.safe_to_decimal128(old_value)
                        updates[field] = new_value
                        needs_update = True
            
            # 執行更新
            if needs_update:
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                updated += 1
            
            # 進度顯示
            if processed % 10000 == 0:
                logger.info(f"已處理: {processed:,}/{total:,} ({processed/total*100:.1f}%) | 已更新: {updated:,}")
        
        logger.info(f"✅ tickers 完成 - 處理: {processed:,} | 更新: {updated:,}")
        self.stats['collections']['tickers'] = {'processed': processed, 'updated': updated}
        self.stats['total_processed'] += processed
        self.stats['total_updated'] += updated
    
    def migrate_financial_reports(self):
        """遷移 financial_reports 集合（財報）"""
        logger.info("=" * 60)
        logger.info("開始遷移 financial_reports 集合")
        logger.info("=" * 60)
        
        collection = self.db.financial_reports
        total = collection.count_documents({})
        logger.info(f"總筆數: {total:,}")
        
        # 三大報表的所有金額欄位
        income_fields = ['revenue', 'grossProfit', 'operatingExpenses', 'operatingIncome',
                        'nonOperatingIncome', 'pretaxIncome', 'incomeTax', 'netIncome', 'eps']
        
        balance_fields = ['totalAssets', 'currentAssets', 'cash', 'accountsReceivable',
                         'inventory', 'fixedAssets', 'intangibleAssets', 'totalLiabilities',
                         'currentLiabilities', 'shortTermDebt', 'longTermDebt',
                         'accountsPayable', 'equity', 'shareCapital', 'retainedEarnings']
        
        cashflow_fields = ['operatingCashFlow', 'investingCashFlow', 'financingCashFlow',
                          'freeCashFlow', 'capitalExpenditure']
        
        processed = 0
        updated = 0
        
        for doc in collection.find():
            processed += 1
            updates = {}
            needs_update = False
            
            # 損益表
            if 'incomeStatement' in doc and doc['incomeStatement']:
                income_updates = {}
                for field in income_fields:
                    if field in doc['incomeStatement']:
                        old_value = doc['incomeStatement'][field]
                        if not isinstance(old_value, Decimal128):
                            income_updates[f'incomeStatement.{field}'] = self.safe_to_decimal128(old_value)
                            needs_update = True
                updates.update(income_updates)
            
            # 資產負債表
            if 'balanceSheet' in doc and doc['balanceSheet']:
                balance_updates = {}
                for field in balance_fields:
                    if field in doc['balanceSheet']:
                        old_value = doc['balanceSheet'][field]
                        if not isinstance(old_value, Decimal128):
                            balance_updates[f'balanceSheet.{field}'] = self.safe_to_decimal128(old_value)
                            needs_update = True
                updates.update(balance_updates)
            
            # 現金流量表
            if 'cashFlow' in doc and doc['cashFlow']:
                cashflow_updates = {}
                for field in cashflow_fields:
                    if field in doc['cashFlow']:
                        old_value = doc['cashFlow'][field]
                        if not isinstance(old_value, Decimal128):
                            cashflow_updates[f'cashFlow.{field}'] = self.safe_to_decimal128(old_value)
                            needs_update = True
                updates.update(cashflow_updates)
            
            if needs_update:
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                updated += 1
            
            if processed % 1000 == 0:
                logger.info(f"已處理: {processed:,}/{total:,} ({processed/total*100:.1f}%) | 已更新: {updated:,}")
        
        logger.info(f"✅ financial_reports 完成 - 處理: {processed:,} | 更新: {updated:,}")
        self.stats['collections']['financial_reports'] = {'processed': processed, 'updated': updated}
        self.stats['total_processed'] += processed
        self.stats['total_updated'] += updated
    
    def migrate_dividends(self):
        """遷移 dividends 集合（股利）"""
        logger.info("=" * 60)
        logger.info("開始遷移 dividends 集合")
        logger.info("=" * 60)
        
        collection = self.db.dividends
        total = collection.count_documents({})
        logger.info(f"總筆數: {total:,}")
        
        dividend_fields = ['cashDividend', 'stockDividend', 'totalDividend', 
                          'dividendYield', 'exDividendPrice']
        
        processed = 0
        updated = 0
        
        for doc in collection.find():
            processed += 1
            updates = {}
            needs_update = False
            
            for field in dividend_fields:
                if field in doc:
                    old_value = doc[field]
                    if not isinstance(old_value, Decimal128):
                        updates[field] = self.safe_to_decimal128(old_value)
                        needs_update = True
            
            if needs_update:
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                updated += 1
        
        logger.info(f"✅ dividends 完成 - 處理: {processed:,} | 更新: {updated:,}")
        self.stats['collections']['dividends'] = {'processed': processed, 'updated': updated}
        self.stats['total_processed'] += processed
        self.stats['total_updated'] += updated
    
    def migrate_valuation_rivers(self):
        """遷移 valuation_rivers 集合（河流圖）"""
        logger.info("=" * 60)
        logger.info("開始遷移 valuation_rivers 集合")
        logger.info("=" * 60)
        
        collection = self.db.valuation_rivers
        total = collection.count_documents({})
        logger.info(f"總筆數: {total:,}")
        
        valuation_fields = ['currentPrice', 'currentPE', 'currentPB', 
                           'pePercentile', 'pbPercentile', 'valuationScore']
        
        processed = 0
        updated = 0
        
        for doc in collection.find():
            processed += 1
            updates = {}
            needs_update = False
            
            for field in valuation_fields:
                if field in doc:
                    old_value = doc[field]
                    if not isinstance(old_value, Decimal128):
                        updates[field] = self.safe_to_decimal128(old_value)
                        needs_update = True
            
            if needs_update:
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                updated += 1
        
        logger.info(f"✅ valuation_rivers 完成 - 處理: {processed:,} | 更新: {updated:,}")
        self.stats['collections']['valuation_rivers'] = {'processed': processed, 'updated': updated}
        self.stats['total_processed'] += processed
        self.stats['total_updated'] += updated
    
    def migrate_monthly_revenues(self):
        """遷移 monthly_revenues 集合（月營收）"""
        logger.info("=" * 60)
        logger.info("開始遷移 monthly_revenues 集合")
        logger.info("=" * 60)
        
        collection = self.db.monthly_revenues
        total = collection.count_documents({})
        logger.info(f"總筆數: {total:,}")
        
        revenue_fields = ['revenue', 'yoyGrowth', 'momGrowth']
        
        processed = 0
        updated = 0
        
        for doc in collection.find():
            processed += 1
            updates = {}
            needs_update = False
            
            for field in revenue_fields:
                if field in doc:
                    old_value = doc[field]
                    if not isinstance(old_value, Decimal128):
                        updates[field] = self.safe_to_decimal128(old_value)
                        needs_update = True
            
            if needs_update:
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': updates}
                )
                updated += 1
        
        logger.info(f"✅ monthly_revenues 完成 - 處理: {processed:,} | 更新: {updated:,}")
        self.stats['collections']['monthly_revenues'] = {'processed': processed, 'updated': updated}
        self.stats['total_processed'] += processed
        self.stats['total_updated'] += updated
    
    def run_migration(self):
        """執行完整遷移"""
        logger.info("🚀 開始資料庫 Schema 遷移：Float → Decimal128")
        logger.info(f"開始時間：{datetime.now()}")
        logger.info("")
        
        start_time = datetime.now()
        
        try:
            # 遷移各個集合
            self.migrate_tickers()
            self.migrate_financial_reports()
            self.migrate_dividends()
            self.migrate_valuation_rivers()
            self.migrate_monthly_revenues()
            
            # 完成報告
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("🎉 遷移完成！")
            logger.info("=" * 60)
            logger.info(f"總處理筆數：{self.stats['total_processed']:,}")
            logger.info(f"總更新筆數：{self.stats['total_updated']:,}")
            logger.info(f"錯誤數量：{self.stats['errors']}")
            logger.info(f"執行時間：{duration:.2f} 秒")
            logger.info("")
            logger.info("各集合詳情：")
            for coll_name, coll_stats in self.stats['collections'].items():
                logger.info(f"  - {coll_name}: 處理 {coll_stats['processed']:,} | 更新 {coll_stats['updated']:,}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 遷移失敗：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


def main():
    """主函數"""
    print("\n")
    print("=" * 70)
    print(" 資料庫 Schema 遷移工具")
    print(" 功能：將所有金額/價格欄位從 Float 轉換為 Decimal128")
    print("=" * 70)
    print("\n⚠️  執行前確認：")
    print("  1. 資料庫已備份（mongodump）")
    print("  2. 確認有足夠的磁碟空間")
    print("  3. 建議在非營業時間執行")
    print("")
    
    response = input("確認要開始遷移嗎？(yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ 已取消遷移")
        return
    
    # 執行遷移
    migrator = SchemaDecimalMigrator()
    success = migrator.run_migration()
    
    if success:
        print("\n✅ 遷移成功！下一步：")
        print("  1. 執行驗證腳本：python scripts/database/verify_decimal_migration.py")
        print("  2. 更新程式碼以使用 Decimal128")
        print("  3. 更新 NestJS Schema 定義")
    else:
        print("\n❌ 遷移失敗，請檢查日誌")
        print("  如需回滾：mongorestore --drop backup_20260220/mongodb_backup/")


if __name__ == '__main__':
    main()
