#!/usr/bin/env python3
"""
MongoDB 集合整合腳本

用途: 自動化整合 MongoDB 集合，消除重複和無用數據

執行方式:
  python3 scripts/consolidate_collections.py --phase 1  # 刪除無用集合
  python3 scripts/consolidate_collections.py --phase 2  # 整合財報數據
  python3 scripts/consolidate_collections.py --backup   # 僅備份

作者: AI Assistant
日期: 2026-02-17
"""

import pymongo
from datetime import datetime
import argparse
import sys
import subprocess
from pathlib import Path

class CollectionConsolidator:
    """MongoDB 集合整合工具"""
    
    def __init__(self, db_uri='mongodb://localhost:27017/', db_name='tw_stock_analysis'):
        self.client = pymongo.MongoClient(db_uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]
        self.db_name = db_name
        
    def backup_database(self):
        """備份資料庫"""
        print("=" * 80)
        print("📦 資料庫備份")
        print("=" * 80)
        print()
        
        backup_dir = Path.home() / 'mongodb_backups'
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'backup_{timestamp}'
        
        print(f"備份目錄: {backup_path}")
        print("開始備份...")
        
        try:
            result = subprocess.run([
                'mongodump',
                '--db', self.db_name,
                '--out', str(backup_path)
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                print("✅ 備份完成")
                print(f"📁 備份位置: {backup_path}")
                return True
            else:
                print("❌ 備份失敗")
                print(result.stderr)
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ 備份超時")
            return False
        except Exception as e:
            print(f"❌ 備份錯誤: {e}")
            return False
    
    def list_collections(self):
        """列出所有集合"""
        collections = self.db.list_collection_names()
        
        print("=" * 80)
        print(f"📊 當前集合列表 (共 {len(collections)} 個)")
        print("=" * 80)
        print()
        
        for i, coll in enumerate(sorted(collections), 1):
            count = self.db[coll].count_documents({})
            print(f"{i:2d}. {coll:30s} {count:>10,} 筆")
        
        print()
        return collections
    
    def phase_1_delete_empty(self):
        """第一階段：刪除空集合和無用數據"""
        print("=" * 80)
        print("🗑️  第一階段：刪除無用集合")
        print("=" * 80)
        print()
        
        deleted_count = 0
        
        # 1. 刪除空集合 - financial_reports
        print("1️⃣  檢查空集合...")
        if 'financial_reports' in self.db.list_collection_names():
            count = self.db.financial_reports.count_documents({})
            if count == 0:
                self.db.financial_reports.drop()
                print(f"   ✅ 已刪除空集合: financial_reports")
                deleted_count += 1
            else:
                print(f"   ⚠️  financial_reports 有 {count} 筆數據，跳過")
        else:
            print("   ℹ️  financial_reports 不存在")
        
        print()
        
        # 2. 刪除測試數據 - yahoo_prices
        print("2️⃣  檢查測試數據...")
        if 'yahoo_prices' in self.db.list_collection_names():
            count = self.db.yahoo_prices.count_documents({})
            print(f"   📊 yahoo_prices: {count} 筆")
            
            if count <= 10:  # 如果只有少量數據，應該是測試用
                confirm = input("   ⚠️  是否刪除 yahoo_prices? (yes/no): ")
                if confirm.lower() == 'yes':
                    self.db.yahoo_prices.drop()
                    print("   ✅ 已刪除: yahoo_prices")
                    deleted_count += 1
                else:
                    print("   ⏭️  跳過 yahoo_prices")
            else:
                print(f"   ⚠️  yahoo_prices 有 {count} 筆數據，建議保留")
        else:
            print("   ℹ️  yahoo_prices 不存在")
        
        print()
        
        # 3. 檢查並刪除重複集合 - stocks vs company_basic_info
        print("3️⃣  檢查重複集合...")
        
        if 'stocks' in self.db.list_collection_names() and \
           'company_basic_info' in self.db.list_collection_names():
            
            stocks_count = self.db.stocks.count_documents({})
            company_count = self.db.company_basic_info.count_documents({})
            
            print(f"   📊 stocks: {stocks_count:,} 筆")
            print(f"   📊 company_basic_info: {company_count:,} 筆")
            print(f"   📊 差異: {abs(stocks_count - company_count)} 筆")
            
            # 檢查結構是否相同
            stocks_sample = self.db.stocks.find_one({})
            company_sample = self.db.company_basic_info.find_one({})
            
            if stocks_sample and company_sample:
                stocks_fields = set(stocks_sample.keys()) - {'_id'}
                company_fields = set(company_sample.keys()) - {'_id'}
                
                if stocks_fields == company_fields:
                    print("   ✅ 欄位結構完全相同")
                    
                    if abs(stocks_count - company_count) <= 10:
                        confirm = input("\n   ⚠️  是否刪除 company_basic_info (保留 stocks)? (yes/no): ")
                        if confirm.lower() == 'yes':
                            self.db.company_basic_info.drop()
                            print("   ✅ 已刪除重複集合: company_basic_info")
                            deleted_count += 1
                        else:
                            print("   ⏭️  保留 company_basic_info")
                    else:
                        print("   ⚠️  數量差異較大，建議手動檢查")
                else:
                    print("   ⚠️  欄位結構不同，建議手動檢查")
                    print(f"   stocks 特有: {stocks_fields - company_fields}")
                    print(f"   company 特有: {company_fields - stocks_fields}")
        else:
            print("   ℹ️  未發現 stocks 和 company_basic_info 同時存在")
        
        print()
        print("=" * 80)
        print(f"✅ 第一階段完成 (刪除 {deleted_count} 個集合)")
        print("=" * 80)
        
        return deleted_count
    
    def phase_2_merge_financials(self):
        """第二階段：整合財報數據"""
        print("=" * 80)
        print("🔄 第二階段：整合財報數據")
        print("=" * 80)
        print()
        
        # 檢查是否存在源集合
        has_finmind = 'finmind_financials' in self.db.list_collection_names()
        has_yahoo = 'yahoo_financials' in self.db.list_collection_names()
        
        if not has_finmind and not has_yahoo:
            print("⚠️  沒有財報數據可整合")
            return 0
        
        finmind_count = self.db.finmind_financials.count_documents({}) if has_finmind else 0
        yahoo_count = self.db.yahoo_financials.count_documents({}) if has_yahoo else 0
        
        print(f"📊 finmind_financials: {finmind_count} 筆")
        print(f"📊 yahoo_financials: {yahoo_count} 筆")
        print(f"📊 總計: {finmind_count + yahoo_count} 筆")
        print()
        
        if finmind_count + yahoo_count == 0:
            print("⚠️  沒有數據需要遷移")
            return 0
        
        # 創建新集合
        if 'financial_statements' not in self.db.list_collection_names():
            self.db.create_collection('financial_statements')
            print("✅ 創建新集合: financial_statements")
        else:
            existing_count = self.db.financial_statements.count_documents({})
            print(f"ℹ️  financial_statements 已存在 ({existing_count} 筆)")
            
            if existing_count > 0:
                confirm = input("⚠️  是否清空並重新整合? (yes/no): ")
                if confirm.lower() == 'yes':
                    self.db.financial_statements.drop()
                    self.db.create_collection('financial_statements')
                    print("✅ 已清空並重建 financial_statements")
                else:
                    print("⏭️  保持現有數據，追加新數據")
        
        print()
        
        # 遷移 FinMind 數據
        if has_finmind and finmind_count > 0:
            print(f"1️⃣  遷移 FinMind 數據 ({finmind_count} 筆)...")
            migrated = 0
            
            for doc in self.db.finmind_financials.find():
                try:
                    self.db.financial_statements.insert_one({
                        'symbol': doc.get('symbol'),
                        'year': doc.get('year'),
                        'season': doc.get('season'),
                        'source': 'finmind',
                        'data': doc,
                        'createTime': doc.get('date'),
                        'updateTime': datetime.now()
                    })
                    migrated += 1
                except Exception as e:
                    print(f"   ⚠️  錯誤: {e}")
            
            print(f"   ✅ 成功遷移 {migrated}/{finmind_count} 筆")
        
        print()
        
        # 遷移 Yahoo 數據
        if has_yahoo and yahoo_count > 0:
            print(f"2️⃣  遷移 Yahoo 數據 ({yahoo_count} 筆)...")
            migrated = 0
            
            for doc in self.db.yahoo_financials.find():
                try:
                    stock_id = doc.get('stockId', '').replace('.TW', '')
                    self.db.financial_statements.insert_one({
                        'symbol': stock_id,
                        'source': 'yahoo',
                        'data': doc,
                        'createTime': doc.get('downloadTime'),
                        'updateTime': datetime.now()
                    })
                    migrated += 1
                except Exception as e:
                    print(f"   ⚠️  錯誤: {e}")
            
            print(f"   ✅ 成功遷移 {migrated}/{yahoo_count} 筆")
        
        print()
        
        # 驗證
        total = self.db.financial_statements.count_documents({})
        expected = finmind_count + yahoo_count
        
        print(f"3️⃣  驗證數據...")
        print(f"   預期: {expected} 筆")
        print(f"   實際: {total} 筆")
        
        if total >= expected:
            print("   ✅ 數據驗證通過")
            print()
            
            confirm = input("⚠️  是否刪除舊集合 (finmind_financials, yahoo_financials)? (yes/no): ")
            if confirm.lower() == 'yes':
                deleted = 0
                if has_finmind:
                    self.db.finmind_financials.drop()
                    print("   ✅ 已刪除: finmind_financials")
                    deleted += 1
                if has_yahoo:
                    self.db.yahoo_financials.drop()
                    print("   ✅ 已刪除: yahoo_financials")
                    deleted += 1
                
                print()
                print("=" * 80)
                print(f"✅ 第二階段完成 (整合並刪除 {deleted} 個舊集合)")
                print("=" * 80)
                
                return deleted
            else:
                print("   ⏭️  保留舊集合供驗證")
                print()
                print("=" * 80)
                print("✅ 第二階段完成 (保留舊集合)")
                print("=" * 80)
                return 0
        else:
            print("   ❌ 數據驗證失敗")
            print("   ⚠️  保留所有集合，請手動檢查")
            return 0
    
    def close(self):
        """關閉連接"""
        self.client.close()

def main():
    parser = argparse.ArgumentParser(
        description='MongoDB 集合整合工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 僅備份
  python3 scripts/consolidate_collections.py --backup
  
  # 列出所有集合
  python3 scripts/consolidate_collections.py --list
  
  # 執行第一階段（刪除無用集合）
  python3 scripts/consolidate_collections.py --phase 1
  
  # 執行第二階段（整合財報）
  python3 scripts/consolidate_collections.py --phase 2
        """
    )
    
    parser.add_argument('--phase', type=int, choices=[1, 2],
                       help='執行階段: 1=刪除無用集合, 2=整合財報')
    parser.add_argument('--backup', action='store_true',
                       help='僅執行備份')
    parser.add_argument('--list', action='store_true',
                       help='列出所有集合')
    parser.add_argument('--db-uri', default='mongodb://localhost:27017/',
                       help='MongoDB 連接字串 (預設: mongodb://localhost:27017/)')
    parser.add_argument('--db-name', default='tw_stock_analysis',
                       help='資料庫名稱 (預設: tw_stock_analysis)')
    
    args = parser.parse_args()
    
    # 如果沒有指定任何操作，顯示幫助
    if not any([args.phase, args.backup, args.list]):
        parser.print_help()
        sys.exit(0)
    
    # 創建整合工具
    try:
        consolidator = CollectionConsolidator(args.db_uri, args.db_name)
        
        print()
        print("=" * 80)
        print("🔧 MongoDB 集合整合工具")
        print("=" * 80)
        print(f"資料庫: {args.db_name}")
        print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        
        # 列出集合
        if args.list:
            consolidator.list_collections()
        
        # 備份
        if args.backup or args.phase:
            if not consolidator.backup_database():
                print("\n⚠️  備份失敗，是否繼續? (yes/no): ", end='')
                if input().lower() != 'yes':
                    print("❌ 操作取消")
                    sys.exit(1)
            print()
        
        # 執行整合
        if args.phase == 1:
            consolidator.phase_1_delete_empty()
            print()
            consolidator.list_collections()
            
        elif args.phase == 2:
            consolidator.phase_2_merge_financials()
            print()
            consolidator.list_collections()
        
        consolidator.close()
        
        print()
        print("=" * 80)
        print("✅ 所有操作完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
