#!/usr/bin/env python3
"""
P0 關鍵問題修復腳本
====================
1. 清理價格異常資料（high/low 缺失）
2. 從 dividend_detail 計算還原權值因子
3. 驗證資料品質

執行前提：MongoDB 正在運行
"""

import sys
from pathlib import Path
from pymongo import MongoClient
from datetime import datetime
from decimal import Decimal
from bson.decimal128 import Decimal128
import logging

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class P0Fixer:
    """P0 問題修復器"""
    
    def __init__(self, mongo_uri="mongodb://localhost:27017/", db_name="tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.stats = {
            'price_fixed': 0,
            'price_deleted': 0,
            'dividend_processed': 0,
            'dividend_failed': 0
        }
    
    def fix_price_anomalies(self):
        """修復價格異常資料"""
        logger.info("\n" + "="*80)
        logger.info("🔧 步驟 1: 修復價格異常資料")
        logger.info("="*80)
        
        # 查找 high 或 low 缺失的記錄
        query = {
            '$or': [
                {'high': None},
                {'low': None},
                {'high': {'$exists': False}},
                {'low': {'$exists': False}}
            ]
        }
        
        total_anomalies = self.db.stock_price.count_documents(query)
        logger.info(f"📊 發現 {total_anomalies:,} 筆 high/low 缺失的記錄")
        
        if total_anomalies == 0:
            logger.info("✅ 無需修復")
            return
        
        # 策略：如果 high/low 缺失但 closePrice 存在，則刪除這些記錄
        # （因為沒有 high/low 的價格資料無法進行技術分析）
        logger.info("🗑️  刪除無效記錄（僅有收盤價但缺少最高/最低價）...")
        
        result = self.db.stock_price.delete_many(query)
        self.stats['price_deleted'] = result.deleted_count
        
        logger.info(f"✅ 已刪除 {result.deleted_count:,} 筆無效記錄")
        logger.info(f"📈 剩餘有效記錄: {self.db.stock_price.count_documents({}):,} 筆")
    
    def process_dividend_data(self):
        """處理股利資料並計算還原權值因子"""
        logger.info("\n" + "="*80)
        logger.info("🔧 步驟 2: 處理股利資料並計算還原權值因子")
        logger.info("="*80)
        
        # 獲取所有 dividend_detail 資料（僅現金股利 > 0）
        dividends = list(self.db.dividend_detail.find({
            'CashEarningsDistribution': {'$gt': 0}
        }).sort([('stock_id', 1), ('date', 1)]))
        
        total = len(dividends)
        logger.info(f"📊 找到 {total:,} 筆有效股利明細資料（現金股利 > 0）")
        
        if total == 0:
            logger.warning("⚠️  無股利資料可處理")
            return
        
        processed = 0
        failed = 0
        no_price_data = 0
        
        for idx, div in enumerate(dividends, 1):
            try:
                stock_id = div.get('stock_id')
                ex_date = div.get('CashExDividendTradingDate')
                
                # 跳過缺少必要欄位的記錄
                if not stock_id or not ex_date or ex_date == '':
                    failed += 1
                    continue
                
                # 提取現金股利
                cash_dividend = float(div.get('CashEarningsDistribution', 0))
                
                # 查詢除息日前一天的價格（date 是字串格式）
                # 使用字串比較 (YYYY-MM-DD 格式可直接比較)
                price_data = self.db.stock_price.find_one(
                    {
                        'stock_id': stock_id,
                        'date': {'$lt': ex_date}
                    },
                    sort=[('date', -1)]
                )
                
                if not price_data:
                    no_price_data += 1
                    failed += 1
                    if idx <= 10:  # 只記錄前 10 個
                        logger.debug(f"⚠️  找不到價格資料: {stock_id} 除息日 {ex_date}")
                    continue
                
                # 計算還原權值因子
                close_price = float(price_data['closePrice'].to_decimal())
                if close_price <= 0:
                    failed += 1
                    continue
                
                # 除息參考價 = 收盤價 - 現金股利
                ex_dividend_ref_price = close_price - cash_dividend
                
                # 還原權值因子 = 收盤價 / 除息參考價
                if ex_dividend_ref_price <= 0:
                    # 股利大於股價的極端情況（罕見）
                    adjustment_factor = Decimal128(Decimal('1.0'))
                    logger.warning(f"⚠️  異常: {stock_id} 除息日 {ex_date} 股利 {cash_dividend} > 收盤價 {close_price}")
                else:
                    adjustment_factor = Decimal128(
                        Decimal(str(close_price)) / Decimal(str(ex_dividend_ref_price))
                    )
                
                # 儲存到 dividend_results
                result_doc = {
                    'stock_id': stock_id,
                    'date': ex_date,
                    'before_price': Decimal128(Decimal(str(close_price))),
                    'reference_price': Decimal128(Decimal(str(ex_dividend_ref_price))),
                    'cash_dividend': Decimal128(Decimal(str(cash_dividend))),
                    'stock_dividend': div.get('StockEarningsDistribution', 0),
                    'adjustmentFactor': adjustment_factor,
                    'ex_dividend_date': ex_date,
                    'cash_dividend_payout_date': div.get('CashDividendPaymentDate', ''),
                    'year': div.get('year', ''),
                    'updated_at': datetime.now()
                }
                
                # Upsert
                self.db.dividend_results.update_one(
                    {'stock_id': stock_id, 'date': ex_date},
                    {'$set': result_doc},
                    upsert=True
                )
                
                processed += 1
                
                if idx % 500 == 0:
                    logger.info(f"⏳ 進度: {idx}/{total} ({idx/total*100:.1f}%) - 已處理 {processed} 筆")
                
            except Exception as e:
                logger.debug(f"⚠️  處理失敗 {div.get('stock_id')} {div.get('CashExDividendTradingDate')}: {e}")
                failed += 1
        
        self.stats['dividend_processed'] = processed
        self.stats['dividend_failed'] = failed
        
        logger.info(f"\n✅ 股利資料處理完成:")
        logger.info(f"   成功: {processed:,} 筆")
        logger.info(f"   失敗: {failed:,} 筆 (其中 {no_price_data} 筆找不到價格資料)")
        logger.info(f"   總計 dividend_results: {self.db.dividend_results.count_documents({}):,} 筆")
    
    def verify_data_quality(self):
        """驗證修復後的資料品質"""
        logger.info("\n" + "="*80)
        logger.info("✅ 步驟 3: 驗證資料品質")
        logger.info("="*80)
        
        # 1. 檢查價格資料
        total_prices = self.db.stock_price.count_documents({})
        valid_prices = self.db.stock_price.count_documents({
            'high': {'$exists': True, '$ne': None},
            'low': {'$exists': True, '$ne': None},
            'closePrice': {'$exists': True, '$ne': None}
        })
        
        logger.info(f"📊 價格資料:")
        logger.info(f"   總筆數: {total_prices:,}")
        logger.info(f"   有效筆數: {valid_prices:,}")
        logger.info(f"   有效率: {valid_prices/total_prices*100:.2f}%")
        
        # 2. 檢查價格邏輯
        logic_errors = self.db.stock_price.count_documents({
            '$or': [
                {'$expr': {'$lt': ['$high', '$closePrice']}},
                {'$expr': {'$lt': ['$closePrice', '$low']}}
            ]
        })
        
        logger.info(f"\n📊 價格邏輯:")
        logger.info(f"   邏輯異常: {logic_errors:,} 筆")
        logger.info(f"   邏輯正確率: {(total_prices-logic_errors)/total_prices*100:.2f}%")
        
        # 3. 檢查股利資料
        total_dividends = self.db.dividend_results.count_documents({})
        stocks_with_dividends = len(self.db.dividend_results.distinct('stock_id'))
        
        logger.info(f"\n📊 股利資料:")
        logger.info(f"   總筆數: {total_dividends:,}")
        logger.info(f"   涵蓋股票: {stocks_with_dividends} 支")
        
        # 4. 檢查 Decimal128
        sample = self.db.stock_price.find_one({}, {'closePrice': 1, 'high': 1, 'low': 1})
        if sample:
            logger.info(f"\n📊 資料型別:")
            logger.info(f"   closePrice: {type(sample.get('closePrice')).__name__}")
            logger.info(f"   high: {type(sample.get('high')).__name__}")
            logger.info(f"   low: {type(sample.get('low')).__name__}")
    
    def print_summary(self):
        """列印執行摘要"""
        logger.info("\n" + "="*80)
        logger.info("📊 P0 修復摘要")
        logger.info("="*80)
        logger.info(f"價格資料:")
        logger.info(f"  已修復: {self.stats['price_fixed']:,} 筆")
        logger.info(f"  已刪除: {self.stats['price_deleted']:,} 筆")
        logger.info(f"\n股利資料:")
        logger.info(f"  已處理: {self.stats['dividend_processed']:,} 筆")
        logger.info(f"  處理失敗: {self.stats['dividend_failed']:,} 筆")
        logger.info("="*80)
    
    def run(self):
        """執行所有修復任務"""
        logger.info("\n🚀 開始執行 P0 關鍵問題修復\n")
        
        try:
            # 步驟 1: 修復價格異常
            self.fix_price_anomalies()
            
            # 步驟 2: 處理股利資料
            self.process_dividend_data()
            
            # 步驟 3: 驗證資料品質
            self.verify_data_quality()
            
            # 列印摘要
            self.print_summary()
            
            logger.info("\n✅ P0 修復完成！")
            return True
            
        except Exception as e:
            logger.error(f"\n❌ 修復過程發生錯誤: {e}", exc_info=True)
            return False
        
        finally:
            self.client.close()


if __name__ == '__main__':
    fixer = P0Fixer()
    success = fixer.run()
    sys.exit(0 if success else 1)
