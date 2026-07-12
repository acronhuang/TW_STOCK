#!/usr/bin/env python3
"""
資料庫 Schema 遷移：統一欄位名稱
- close → closePrice (統一使用 closePrice)
- volume → tradeVolume (統一使用 tradeVolume)
"""

from pymongo import MongoClient
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FieldUnificationMigrator:
    """欄位統一遷移器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        
    def unify_tickers_fields(self):
        """統一 tickers 集合的欄位名稱"""
        logger.info("=" * 60)
        logger.info("統一 tickers 集合欄位名稱")
        logger.info("=" * 60)
        
        collection = self.db.tickers
        
        # 步驟 1: 確保所有文件都有首選欄位（從相容欄位複製）
        logger.info("步驟 1: 複製相容欄位到首選欄位（如果缺失）")
        
        # close → closePrice
        result1 = collection.update_many(
            {'closePrice': {'$exists': False}, 'close': {'$exists': True}},
            [{'$set': {'closePrice': '$close'}}]
        )
        logger.info(f"  - close → closePrice: {result1.modified_count} 筆")
        
        # volume → tradeVolume
        result2 = collection.update_many(
            {'tradeVolume': {'$exists': False}, 'volume': {'$exists': True}},
            [{'$set': {'tradeVolume': '$volume'}}]
        )
        logger.info(f"  - volume → tradeVolume: {result2.modified_count} 筆")
        
        # 步驟 2: 確保相容欄位與首選欄位一致（雙向同步）
        logger.info("\n步驟 2: 同步首選欄位到相容欄位（向下相容期）")
        
        result3 = collection.update_many(
            {'closePrice': {'$exists': True}},
            [{'$set': {'close': '$closePrice'}}]
        )
        logger.info(f"  - closePrice → close: {result3.modified_count} 筆")
        
        result4 = collection.update_many(
            {'tradeVolume': {'$exists': True}},
            [{'$set': {'volume': '$tradeVolume'}}]
        )
        logger.info(f"  - tradeVolume → volume: {result4.modified_count} 筆")
        
        # 步驟 3: 驗證資料一致性
        logger.info("\n步驟 3: 驗證資料一致性")
        
        # 檢查是否有不一致的文件
        inconsistent_price = collection.count_documents({
            '$expr': {'$ne': ['$close', '$closePrice']}
        })
        
        inconsistent_volume = collection.count_documents({
            '$expr': {'$ne': ['$volume', '$tradeVolume']}
        })
        
        if inconsistent_price > 0:
            logger.warning(f"  ⚠️  發現 {inconsistent_price} 筆 close/closePrice 不一致")
        else:
            logger.info(f"  ✅ close/closePrice 完全一致")
        
        if inconsistent_volume > 0:
            logger.warning(f"  ⚠️  發現 {inconsistent_volume} 筆 volume/tradeVolume 不一致")
        else:
            logger.info(f"  ✅ volume/tradeVolume 完全一致")
        
        # 步驟 4: 建立相容 View（過渡期使用）
        logger.info("\n步驟 4: 建立相容 View（過渡期）")
        
        try:
            # 刪除舊 View（如果存在）
            self.db.tickers_legacy.drop()
            
            # 建立新 View
            self.db.create_collection(
                'tickers_legacy',
                viewOn='tickers',
                pipeline=[
                    {
                        '$addFields': {
                            'close': '$closePrice',
                            'volume': '$tradeVolume'
                        }
                    }
                ]
            )
            logger.info("  ✅ 已建立 tickers_legacy View")
            logger.info("     舊程式碼可暫時使用此 View 查詢")
        except Exception as e:
            logger.warning(f"  ⚠️  建立 View 失敗: {e}")
        
        logger.info("\n✅ tickers 集合欄位統一完成")
        logger.info("\n📝 下一步：")
        logger.info("  1. 更新所有 Python 程式碼使用 closePrice/tradeVolume")
        logger.info("  2. 更新 NestJS Schema 定義")
        logger.info("  3. 驗證所有 API 回傳正確")
        logger.info("  4. 確認無誤後，可刪除相容欄位（執行 remove_legacy_fields.py）")
    
    def run(self):
        """執行遷移"""
        logger.info("🚀 開始欄位統一遷移")
        logger.info(f"時間：{datetime.now()}\n")
        
        try:
            self.unify_tickers_fields()
            return True
        except Exception as e:
            logger.error(f"❌ 遷移失敗：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return False


def main():
    print("\n")
    print("=" * 70)
    print(" 欄位統一遷移工具")
    print(" 功能：統一使用 closePrice/tradeVolume（保留相容欄位）")
    print("=" * 70)
    print("\n⚠️  注意事項：")
    print("  - 此腳本會同步相容欄位（close ↔ closePrice）")
    print("  - 建立 View 供過渡期使用")
    print("  - 不會刪除任何欄位")
    print("")
    
    response = input("確認要開始遷移嗎？(yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ 已取消")
        return
    
    migrator = FieldUnificationMigrator()
    success = migrator.run()
    
    if success:
        print("\n✅ 欄位統一完成！")
    else:
        print("\n❌ 遷移失敗")


if __name__ == '__main__':
    main()
