#!/usr/bin/env python3
"""
數據完整性檢查

檢查現有資料庫數據是否足夠進行 v2.1 策略回測

作者: Ming
創建日期: 2026-02-23
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
from datetime import datetime, timedelta
import pandas as pd


class DataReadinessChecker:
    """數據完整性檢查器"""
    
    def __init__(self, db_name='tw_stock_analysis'):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        
    def check_collection(self, collection_name, stock_field='stock_id', date_field='date'):
        """檢查單一集合"""
        collection = self.db[collection_name]
        
        total_count = collection.count_documents({})
        if total_count == 0:
            return None
        
        stock_count = len(collection.distinct(stock_field))
        
        # 最新和最舊日期
        latest = collection.find_one(sort=[(date_field, -1)])
        oldest = collection.find_one(sort=[(date_field, 1)])
        
        latest_date = latest.get(date_field) if latest else None
        oldest_date = oldest.get(date_field) if oldest else None
        
        return {
            'collection': collection_name,
            'total_records': total_count,
            'stock_count': stock_count,
            'latest_date': latest_date,
            'oldest_date': oldest_date
        }
    
    def check_all_collections(self):
        """檢查所有必要集合"""
        print("="*70)
        print("數據完整性檢查")
        print("="*70)
        
        # 必要的集合
        required_collections = {
            'stock_price': {
                'description': '股價日線數據',
                'stock_field': 'stock_id',
                'date_field': 'date',
                'required': True
            },
            'financial_reports': {
                'description': '財務報表',
                'stock_field': 'symbol',
                'date_field': 'date',
                'required': True
            },
            'taiwan_stock_per': {
                'description': '本益比數據',
                'stock_field': 'stock_id',
                'date_field': 'date',
                'required': True
            },
            'dividend': {
                'description': '除權息數據',
                'stock_field': 'stock_id',
                'date_field': 'date',
                'required': True
            },
            'institutional_holdings': {
                'description': '大戶持股',
                'stock_field': 'stock_id',
                'date_field': 'date',
                'required': False
            },
            'institutional_trading': {
                'description': '法人買賣',
                'stock_field': 'stock_id',
                'date_field': 'date',
                'required': False
            }
        }
        
        results = {}
        all_ready = True
        
        for coll_name, config in required_collections.items():
            print(f"\n檢查 {config['description']} ({coll_name})...")
            
            result = self.check_collection(
                coll_name,
                config['stock_field'],
                config['date_field']
            )
            
            if result is None:
                print(f"  ✗ 無數據")
                if config['required']:
                    all_ready = False
                results[coll_name] = None
            else:
                results[coll_name] = result
                print(f"  ✓ 總記錄: {result['total_records']:,}")
                print(f"  ✓ 股票數: {result['stock_count']}")
                print(f"  ✓ 日期範圍: {result['oldest_date']} ~ {result['latest_date']}")
                
                # 檢查數據新鮮度（最新數據是否在 7 天內）
                if result['latest_date']:
                    try:
                        if isinstance(result['latest_date'], str):
                            latest = datetime.strptime(result['latest_date'], '%Y-%m-%d')
                        else:
                            latest = result['latest_date']
                        
                        days_old = (datetime.now() - latest).days
                        
                        if days_old > 7:
                            print(f"  ⚠️  數據較舊（{days_old} 天前）")
                        else:
                            print(f"  ✓ 數據新鮮（{days_old} 天前）")
                    except:
                        pass
        
        return results, all_ready
    
    def check_factor_data(self):
        """檢查因子數據"""
        print(f"\n{'='*70}")
        print("因子數據檢查")
        print(f"{'='*70}")
        
        # 檢查 17 因子
        factors_to_check = [
            'return_3m', 'return_6m', 'return_12m',
            'volatility_3m', 'volume_ratio_20d',
            'rsi_14d', 'macd',
            'roe', 'roa', 'gross_margin', 'operating_margin',
            'debt_ratio', 'current_ratio',
            'pb_ratio', 'pe_ratio', 'dividend_yield', 'eps_growth'
        ]
        
        # 從 stock_price 檢查技術因子
        sample = self.db.stock_price.find_one(
            {'return_3m': {'$exists': True}},
            sort=[('date', -1)]
        )
        
        if sample:
            print("\n技術因子:")
            tech_factors = ['return_3m', 'return_6m', 'return_12m', 
                           'volatility_3m', 'volume_ratio_20d', 'rsi_14d', 'macd']
            
            existing_tech = [f for f in tech_factors if f in sample]
            print(f"  ✓ 已計算: {len(existing_tech)}/{len(tech_factors)}")
            print(f"    {', '.join(existing_tech)}")
            
            if len(existing_tech) < len(tech_factors):
                missing = [f for f in tech_factors if f not in sample]
                print(f"  ⚠️  缺少: {', '.join(missing)}")
        else:
            print("\n技術因子:")
            print("  ✗ 未計算")
        
        # 從 financial_reports 檢查基本面因子
        sample = self.db.financial_reports.find_one(
            {'roe': {'$exists': True}},
            sort=[('date', -1)]
        )
        
        if sample:
            print("\n基本面因子:")
            fundamental_factors = ['roe', 'roa', 'gross_margin', 'operating_margin',
                                  'debt_ratio', 'current_ratio']
            
            existing_fund = [f for f in fundamental_factors if f in sample]
            print(f"  ✓ 已計算: {len(existing_fund)}/{len(fundamental_factors)}")
            print(f"    {', '.join(existing_fund)}")
            
            if len(existing_fund) < len(fundamental_factors):
                missing = [f for f in fundamental_factors if f not in sample]
                print(f"  ⚠️  缺少: {', '.join(missing)}")
        else:
            print("\n基本面因子:")
            print("  ✗ 未計算")
        
        # 檢查估值因子
        sample = self.db.taiwan_stock_per.find_one(
            {'pe_ratio': {'$exists': True}},
            sort=[('date', -1)]
        )
        
        if sample:
            print("\n估值因子:")
            print(f"  ✓ PE/PB 數據可用")
        else:
            print("\n估值因子:")
            print("  ⚠️  PE/PB 數據不完整")
    
    def generate_report(self):
        """生成完整報告"""
        results, all_ready = self.check_all_collections()
        self.check_factor_data()
        
        print(f"\n{'='*70}")
        print("總結")
        print(f"{'='*70}")
        
        if all_ready:
            print("\n✅ 數據完整，可以進行策略回測！")
            print("\n建議下一步：")
            print("  1. 執行 v2.0 vs v2.1 回測對比")
            print("     python3 scripts/backtest_integrated_v21.py \\")
            print("         --start-date 2023-01-01 \\")
            print("         --end-date 2024-12-31")
            print("\n  2. 如需更多數據，等待 24 小時後繼續同步")
            print("     或升級到 FinMind Premium")
        else:
            print("\n⚠️  關鍵數據缺失")
            print("\n需要執行：")
            
            missing_collections = [k for k, v in results.items() if v is None]
            if missing_collections:
                print(f"  缺少集合: {', '.join(missing_collections)}")
            
            print("\n建議：")
            print("  1. 等待 24 小時後執行完整同步")
            print("  2. 或升級到 FinMind Premium 版本")
            print("  3. 或使用 unified_downloader 補充數據")


def main():
    """主程式"""
    checker = DataReadinessChecker()
    checker.generate_report()


if __name__ == '__main__':
    main()
