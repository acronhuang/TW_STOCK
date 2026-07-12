#!/usr/bin/env python3
"""
測試 Dashboard 日期格式化修復
"""
from pymongo import MongoClient
from datetime import datetime
import sys

def test_date_formats():
    """測試各種日期格式"""
    print("🧪 測試日期格式化修復\n")
    
    # 連接數據庫
    try:
        client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)
        db = client['tw_stock_analysis']
        client.server_info()
        print("✅ MongoDB 連接成功\n")
    except Exception as e:
        print(f"❌ MongoDB 連接失敗: {e}")
        return False
    
    # 測試股價數據的日期格式
    print("1️⃣  測試 stock_price 日期格式:")
    latest_price = db.stock_price.find_one(
        sort=[('date', -1)],
        projection={'date': 1, 'stock_id': 1}
    )
    
    if latest_price:
        date_value = latest_price['date']
        date_type = type(date_value).__name__
        print(f"   股票ID: {latest_price.get('stock_id', 'N/A')}")
        print(f"   日期值: {date_value}")
        print(f"   日期類型: {date_type}")
        
        # 測試格式化
        try:
            if isinstance(date_value, str):
                print(f"   ✅ 字符串格式 (可直接使用)")
            elif isinstance(date_value, datetime):
                formatted = date_value.strftime('%Y-%m-%d')
                print(f"   ✅ datetime 對象 (格式化: {formatted})")
            else:
                print(f"   ⚠️  未知類型: {date_type}")
        except Exception as e:
            print(f"   ❌ 格式化失敗: {e}")
    else:
        print("   ⚠️  無數據")
    
    print()
    
    # 測試財報數據的日期格式
    print("2️⃣  測試 financial_reports 日期格式:")
    latest_financial = db.financial_reports.find_one(
        sort=[('reportDate', -1)],
        projection={'reportDate': 1, 'symbol': 1}
    )
    
    if latest_financial:
        date_value = latest_financial['reportDate']
        date_type = type(date_value).__name__
        print(f"   股票代碼: {latest_financial.get('symbol', 'N/A')}")
        print(f"   日期值: {date_value}")
        print(f"   日期類型: {date_type}")
        
        try:
            if isinstance(date_value, str):
                print(f"   ✅ 字符串格式 (可直接使用)")
            elif isinstance(date_value, datetime):
                formatted = date_value.strftime('%Y-%m-%d')
                print(f"   ✅ datetime 對象 (格式化: {formatted})")
            else:
                print(f"   ⚠️  未知類型: {date_type}")
        except Exception as e:
            print(f"   ❌ 格式化失敗: {e}")
    else:
        print("   ⚠️  無數據")
    
    print()
    
    # 測試因子數據的日期格式
    print("3️⃣  測試 stock_factors 日期格式:")
    latest_factor = db.stock_factors.find_one(
        sort=[('date', -1)],
        projection={'date': 1, 'symbol': 1}
    )
    
    if latest_factor:
        date_value = latest_factor['date']
        date_type = type(date_value).__name__
        print(f"   股票代碼: {latest_factor.get('symbol', 'N/A')}")
        print(f"   日期值: {date_value}")
        print(f"   日期類型: {date_type}")
        
        try:
            if isinstance(date_value, str):
                print(f"   ✅ 字符串格式 (可直接使用)")
            elif isinstance(date_value, datetime):
                formatted = date_value.strftime('%Y-%m-%d')
                print(f"   ✅ datetime 對象 (格式化: {formatted})")
            else:
                print(f"   ⚠️  未知類型: {date_type}")
        except Exception as e:
            print(f"   ❌ 格式化失敗: {e}")
    else:
        print("   ⚠️  無數據")
    
    print("\n" + "="*60)
    print("✅ 測試完成")
    return True


if __name__ == '__main__':
    success = test_date_formats()
    sys.exit(0 if success else 1)
