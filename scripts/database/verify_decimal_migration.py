#!/usr/bin/env python3
"""
驗證 Decimal128 遷移結果
檢查資料型態、精度、一致性
"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DecimalMigrationValidator:
    """Decimal128 遷移驗證器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.issues = []
        
    def validate_collection_field_types(self, collection_name: str, numeric_fields: list):
        """驗證集合的欄位型態"""
        logger.info(f"\n檢查 {collection_name} 集合...")
        
        collection = self.db[collection_name]
        total = collection.count_documents({})
        
        if total == 0:
            logger.warning(f"  ⚠️  集合為空")
            return
        
        # 隨機抽樣檢查
        sample_size = min(100, total)
        samples = list(collection.aggregate([{'$sample': {'size': sample_size}}]))
        
        field_stats = {field: {'decimal': 0, 'float': 0, 'other': 0} for field in numeric_fields}
        
        for doc in samples:
            for field in numeric_fields:
                # 處理嵌套欄位（如 incomeStatement.revenue）
                if '.' in field:
                    parts = field.split('.')
                    value = doc
                    for part in parts:
                        if isinstance(value, dict) and part in value:
                            value = value[part]
                        else:
                            value = None
                            break
                else:
                    value = doc.get(field)
                
                if value is None:
                    continue
                
                if isinstance(value, Decimal128):
                    field_stats[field]['decimal'] += 1
                elif isinstance(value, (int, float)):
                    field_stats[field]['float'] += 1
                else:
                    field_stats[field]['other'] += 1
        
        # 報告結果
        all_decimal = True
        for field, stats in field_stats.items():
            total_checked = sum(stats.values())
            if total_checked == 0:
                continue
            
            decimal_pct = (stats['decimal'] / total_checked * 100) if total_checked > 0 else 0
            
            if stats['decimal'] == total_checked:
                logger.info(f"  ✅ {field}: 100% Decimal128")
            elif stats['decimal'] > 0:
                logger.warning(f"  ⚠️  {field}: {decimal_pct:.1f}% Decimal128 (有 {stats['float']} 個 Float)")
                all_decimal = False
                self.issues.append(f"{collection_name}.{field} 未完全轉換")
            else:
                logger.error(f"  ❌ {field}: 0% Decimal128 (全部是 Float)")
                all_decimal = False
                self.issues.append(f"{collection_name}.{field} 完全未轉換")
        
        return all_decimal
    
    def validate_tickers(self):
        """驗證 tickers 集合"""
        fields = [
            'openPrice', 'highPrice', 'lowPrice', 'closePrice',
            'change', 'tradeValue', 'changePercent'
        ]
        return self.validate_collection_field_types('tickers', fields)
    
    def validate_financial_reports(self):
        """驗證 financial_reports 集合"""
        fields = [
            'incomeStatement.revenue',
            'incomeStatement.netIncome',
            'incomeStatement.eps',
            'balanceSheet.totalAssets',
            'balanceSheet.equity',
            'cashFlow.operatingCashFlow',
            'cashFlow.freeCashFlow'
        ]
        return self.validate_collection_field_types('financial_reports', fields)
    
    def validate_dividends(self):
        """驗證 dividends 集合"""
        fields = ['cashDividend', 'stockDividend', 'dividendYield']
        return self.validate_collection_field_types('dividends', fields)
    
    def validate_valuation_rivers(self):
        """驗證 valuation_rivers 集合"""
        fields = ['currentPE', 'currentPB', 'pePercentile', 'pbPercentile']
        return self.validate_collection_field_types('valuation_rivers', fields)
    
    def validate_monthly_revenues(self):
        """驗證 monthly_revenues 集合"""
        fields = ['revenue', 'yoyGrowth', 'momGrowth']
        return self.validate_collection_field_types('monthly_revenues', fields)
    
    def validate_price_logic(self):
        """驗證價格邏輯（high >= close >= low）"""
        logger.info("\n檢查價格邏輯...")
        
        collection = self.db.tickers
        
        # 檢查 high < close 或 close < low 的異常資料
        invalid_high = collection.count_documents({
            '$expr': {'$lt': ['$highPrice', '$closePrice']}
        })
        
        invalid_low = collection.count_documents({
            '$expr': {'$gt': ['$lowPrice', '$closePrice']}
        })
        
        if invalid_high > 0:
            logger.error(f"  ❌ 發現 {invalid_high} 筆 highPrice < closePrice")
            self.issues.append(f"價格邏輯錯誤: {invalid_high} 筆")
        else:
            logger.info(f"  ✅ highPrice >= closePrice 檢查通過")
        
        if invalid_low > 0:
            logger.error(f"  ❌ 發現 {invalid_low} 筆 lowPrice > closePrice")
            self.issues.append(f"價格邏輯錯誤: {invalid_low} 筆")
        else:
            logger.info(f"  ✅ lowPrice <= closePrice 檢查通過")
    
    def validate_precision(self):
        """驗證精度（檢查是否有浮點數誤差）"""
        logger.info("\n檢查精度...")
        
        collection = self.db.tickers
        
        # 抽樣檢查
        sample = collection.find_one({'closePrice': {'$exists': True}})
        
        if sample and 'closePrice' in sample:
            close_value = sample['closePrice']
            
            if isinstance(close_value, Decimal128):
                # 轉換為字串檢查
                close_str = str(close_value)
                
                # 檢查是否有過長的小數位（浮點數誤差特徵）
                if '.' in close_str:
                    decimal_places = len(close_str.split('.')[1])
                    if decimal_places > 10:
                        logger.warning(f"  ⚠️  發現過長小數位數: {decimal_places} 位")
                    else:
                        logger.info(f"  ✅ 精度正常（小數位數: {decimal_places}）")
                else:
                    logger.info(f"  ✅ 整數值")
            else:
                logger.error(f"  ❌ closePrice 不是 Decimal128 型態")
        else:
            logger.warning(f"  ⚠️  無法取得樣本資料")
    
    def run_validation(self):
        """執行完整驗證"""
        logger.info("=" * 60)
        logger.info("🔍 開始驗證 Decimal128 遷移結果")
        logger.info("=" * 60)
        
        # 驗證各集合
        self.validate_tickers()
        self.validate_financial_reports()
        self.validate_dividends()
        self.validate_valuation_rivers()
        self.validate_monthly_revenues()
        
        # 驗證邏輯與精度
        self.validate_price_logic()
        self.validate_precision()
        
        # 總結報告
        logger.info("\n" + "=" * 60)
        logger.info("📊 驗證結果總結")
        logger.info("=" * 60)
        
        if len(self.issues) == 0:
            logger.info("✅ 所有檢查通過！遷移成功！")
            logger.info("\n下一步：")
            logger.info("  1. 更新 Python 程式碼使用 Decimal")
            logger.info("  2. 更新 NestJS Schema 定義")
            logger.info("  3. 測試所有 API 端點")
            return True
        else:
            logger.error(f"❌ 發現 {len(self.issues)} 個問題：")
            for issue in self.issues:
                logger.error(f"  - {issue}")
            logger.error("\n建議：重新執行遷移腳本或手動修正")
            return False


def main():
    print("\n")
    print("=" * 70)
    print(" Decimal128 遷移驗證工具")
    print("=" * 70)
    print("")
    
    validator = DecimalMigrationValidator()
    success = validator.run_validation()
    
    print("")
    if success:
        print("✅ 驗證完成：資料庫遷移成功")
    else:
        print("❌ 驗證失敗：請檢查上述問題")


if __name__ == '__main__':
    main()
