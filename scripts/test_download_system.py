#!/usr/bin/env python3
"""
下載系統測試腳本
測試基本功能是否正常
"""

import sys
import logging
from pathlib import Path

# 加入專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.downloaders.finmind_client import FinMindClient
from src.downloaders.table_config import get_all_tables, get_tables_by_category

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_api_client():
    """測試 API 客戶端"""
    logger.info("\n" + "="*80)
    logger.info("測試 1: FinMind API 客戶端")
    logger.info("="*80)
    
    try:
        # 從環境變數或 .env 獲取 Token
        import os
        token = os.environ.get('FINMIND_API_TOKEN')
        
        if not token:
            # 從 .env 讀取
            env_file = project_root / '.env'
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.startswith('FINMIND_API_TOKEN='):
                            token = line.split('=', 1)[1].strip()
                            break
        
        if not token:
            logger.error("❌ 找不到 FINMIND_API_TOKEN")
            return False
        
        logger.info("✅ API Token 已載入")
        
        # 建立客戶端
        client = FinMindClient(token, logger)
        logger.info("✅ FinMindClient 初始化成功")
        
        # 測試簡單請求
        logger.info("\n測試 API 請求: TaiwanStockInfo...")
        data = client.fetch_data("TaiwanStockInfo", {})
        
        if data:
            logger.info(f"✅ 獲取 {len(data)} 筆資料")
            logger.info(f"   範例: {data[0] if data else 'N/A'}")
            
            # 檢查 API 使用統計
            usage = client.get_api_usage()
            logger.info(f"\n📊 API 使用統計:")
            logger.info(f"   調用次數: {usage['call_count']}/{usage['quota']}")
            logger.info(f"   使用率: {usage['usage_percent']}%")
            logger.info(f"   剩餘: {usage['remaining']}")
            
            return True
        else:
            logger.error("❌ 未獲取到資料")
            return False
            
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}", exc_info=True)
        return False


def test_table_config():
    """測試資料表配置"""
    logger.info("\n" + "="*80)
    logger.info("測試 2: 資料表配置")
    logger.info("="*80)
    
    try:
        # 獲取所有資料表
        all_tables = get_all_tables()
        logger.info(f"✅ 總資料表數: {len(all_tables)}")
        
        # 按類別統計
        categories = ['技術面', '籌碼面', '基本面', '衍生性金融商品', '其他']
        for category in categories:
            tables = get_tables_by_category(category)
            logger.info(f"   {category}: {len(tables)} 個")
        
        # 顯示前 3 個資料表
        logger.info(f"\n前 3 個資料表:")
        for i, table in enumerate(all_tables[:3], 1):
            logger.info(f"   {i}. {table['name']}")
            logger.info(f"      Dataset: {table['dataset']}")
            logger.info(f"      Collection: {table['collection']}")
            logger.info(f"      需要股票代碼: {table.get('needs_symbols', False)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}", exc_info=True)
        return False


def test_mongodb_connection():
    """測試 MongoDB 連線"""
    logger.info("\n" + "="*80)
    logger.info("測試 3: MongoDB 連線")
    logger.info("="*80)
    
    try:
        from pymongo import MongoClient
        
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)
        db = client['tw_stock_analysis']
        
        # 測試連線
        client.admin.command('ping')
        logger.info("✅ MongoDB 連線成功")
        
        # 列出現有集合
        collections = db.list_collection_names()
        logger.info(f"✅ 現有集合數: {len(collections)}")
        
        if collections:
            logger.info(f"   前 5 個集合: {', '.join(collections[:5])}")
        
        # 檢查是否有股票資料
        if 'tickers' in collections:
            count = db.tickers.count_documents({})
            logger.info(f"✅ tickers 集合: {count:,} 筆")
        
        client.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ MongoDB 連線失敗: {e}")
        return False


def test_decimal128_conversion():
    """測試 Decimal128 轉換"""
    logger.info("\n" + "="*80)
    logger.info("測試 4: Decimal128 轉換")
    logger.info("="*80)
    
    try:
        from bson.decimal128 import Decimal128
        from decimal import Decimal
        
        # 測試數據
        test_data = [
            {'price': 123.45, 'volume': 1000000},
            {'price': '234.56', 'volume': '2000000'},
            {'price': None, 'volume': 0}
        ]
        
        # 模擬轉換
        import os
        token = os.environ.get('FINMIND_API_TOKEN')
        if not token:
            env_file = project_root / '.env'
            with open(env_file, 'r') as f:
                for line in f:
                    if line.startswith('FINMIND_API_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                        break
        
        client = FinMindClient(token, logger)
        converted_data = client._convert_to_decimal128(test_data)
        
        logger.info("✅ Decimal128 轉換測試:")
        for i, (orig, conv) in enumerate(zip(test_data, converted_data), 1):
            logger.info(f"   記錄 {i}:")
            logger.info(f"      原始: {orig}")
            logger.info(f"      轉換: {conv}")
            
            # 驗證類型
            if 'price' in conv and conv['price'] is not None:
                if isinstance(conv['price'], Decimal128):
                    logger.info(f"      ✅ price 為 Decimal128")
                else:
                    logger.warning(f"      ⚠️  price 不是 Decimal128: {type(conv['price'])}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 測試失敗: {e}", exc_info=True)
        return False


def main():
    """主程式"""
    logger.info("\n" + "="*80)
    logger.info("🧪 台股下載系統測試")
    logger.info("="*80 + "\n")
    
    results = []
    
    # 執行測試
    tests = [
        ("API 客戶端", test_api_client),
        ("資料表配置", test_table_config),
        ("MongoDB 連線", test_mongodb_connection),
        ("Decimal128 轉換", test_decimal128_conversion)
    ]
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"測試 '{name}' 發生錯誤: {e}")
            results.append((name, False))
    
    # 總結
    logger.info("\n" + "="*80)
    logger.info("📊 測試結果總結")
    logger.info("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        logger.info(f"{status} - {name}")
    
    logger.info(f"\n總計: {passed}/{total} 通過")
    
    if passed == total:
        logger.info("\n🎉 所有測試通過！系統可以使用")
        return 0
    else:
        logger.error(f"\n❌ 有 {total - passed} 個測試失敗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
