#!/usr/bin/env python3
"""
資料下載進度監控腳本
實時顯示資料庫狀態和下載進度
"""

import pymongo
from datetime import datetime
import time
import sys

def check_database_status():
    """檢查資料庫狀態"""
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("=" * 100)
    print(f"📊 資料庫狀態監控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    print()
    
    # 定義所有集合和描述
    collections_info = [
        # 技術面
        ("taiwan_stock_info", "台股總覽", "技術面"),
        ("stock_price", "台灣股價資料表", "技術面"),
        ("taiwan_stock_per", "個股 PER、PBR", "技術面"),
        
        # 籌碼面
        ("margin_purchase_short_sale", "個股融資融劵", "籌碼面"),
        ("institutional_investors_detail", "個股三大法人", "籌碼面"),
        ("shareholding", "外資持股表", "籌碼面"),
        ("total_margin", "整體市場融資融劵", "籌碼面"),
        
        # 基本面
        ("financial_statement_detail", "綜合損益表", "基本面"),
        ("balance_sheet_detail", "資產負債表", "基本面"),
        ("cash_flows_detail", "現金流量表", "基本面"),
        ("dividend_detail", "股利政策表", "基本面"),
        ("month_revenue_detail", "月營收表", "基本面"),
        
        # 其他
        ("gold_price", "黃金價格", "其他"),
        ("crude_oil_price", "原油資料", "其他"),
        ("exchange_rate", "外幣匯率", "其他"),
        
        # 舊有集合
        ("stocks", "股票基本資料 (舊)", "舊有"),
        ("financial_reports", "財報資料 (舊)", "舊有"),
        ("dividends", "股利資料 (舊)", "舊有"),
        ("monthly_revenue", "月營收 (舊)", "舊有"),
    ]
    
    category_stats = {}
    total_records = 0
    
    for collection, description, category in collections_info:
        count = db[collection].count_documents({})
        total_records += count
        
        if category not in category_stats:
            category_stats[category] = []
        
        category_stats[category].append({
            'collection': collection,
            'description': description,
            'count': count
        })
    
    # 按類別顯示
    for category in ['技術面', '籌碼面', '基本面', '其他', '舊有']:
        if category in category_stats:
            print(f"\n【{category}】")
            print("-" * 100)
            
            for item in category_stats[category]:
                status = "✅" if item['count'] > 0 else "⚠️"
                print(f"  {status} {item['description']:30} {item['collection']:35} {item['count']:>15,} 筆")
    
    print()
    print("=" * 100)
    print(f"📊 總計: {total_records:,} 筆資料")
    print("=" * 100)
    
    return total_records

def check_download_coverage():
    """檢查資料覆蓋率"""
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("\n\n" + "=" * 100)
    print("📈 資料覆蓋率分析")
    print("=" * 100)
    
    # 檢查股價資料覆蓋
    total_stocks = db.stocks.count_documents({})
    stocks_with_price = db.stock_price.distinct('stock_id').__len__()
    
    print(f"\n📊 股價資料:")
    print(f"  總股票數: {total_stocks:,} 檔")
    print(f"  有股價資料: {stocks_with_price:,} 檔")
    print(f"  覆蓋率: {stocks_with_price/total_stocks*100:.1f}%")
    
    # 檢查財報資料覆蓋
    stocks_with_financial = db.financial_statement_detail.distinct('stock_id').__len__()
    print(f"\n📊 財報資料:")
    print(f"  總股票數: {total_stocks:,} 檔")
    print(f"  有財報資料: {stocks_with_financial:,} 檔")
    print(f"  覆蓋率: {stocks_with_financial/total_stocks*100:.1f}%")
    
    # 檢查三大法人資料
    stocks_with_inst = db.institutional_investors_detail.distinct('stock_id').__len__()
    print(f"\n📊 三大法人資料:")
    print(f"  總股票數: {total_stocks:,} 檔")
    print(f"  有法人資料: {stocks_with_inst:,} 檔")
    print(f"  覆蓋率: {stocks_with_inst/total_stocks*100:.1f}%")
    
    print("\n" + "=" * 100)

def check_latest_data():
    """檢查最新資料時間"""
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print("\n\n" + "=" * 100)
    print("🆕 最新資料時間")
    print("=" * 100)
    
    collections_to_check = [
        ('stock_price', '股價'),
        ('financial_statement_detail', '財報'),
        ('institutional_investors_detail', '三大法人'),
        ('month_revenue_detail', '月營收'),
    ]
    
    for collection, name in collections_to_check:
        latest = db[collection].find_one(sort=[('date', -1)])
        if latest and 'date' in latest:
            print(f"  {name:15} 最新資料: {latest['date']}")
        else:
            print(f"  {name:15} 無資料")
    
    print("=" * 100)

def main():
    """主程序"""
    if len(sys.argv) > 1 and sys.argv[1] == '--watch':
        # 監控模式 - 每 10 秒更新一次
        try:
            while True:
                print("\033[2J\033[H")  # 清屏
                check_database_status()
                check_download_coverage()
                check_latest_data()
                print("\n⏰ 下次更新: 10 秒後 (Ctrl+C 停止)")
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n\n✅ 監控已停止")
    else:
        # 單次檢查模式
        check_database_status()
        check_download_coverage()
        check_latest_data()

if __name__ == "__main__":
    main()
