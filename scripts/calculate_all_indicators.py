#!/usr/bin/env python3
"""
完整資料計算系統 - 整合執行
執行所有需要計算的指標: 多空、同業比較、河流圖
"""

import sys
sys.path.append('/home/mdsadmin/Stock/tw-stock-analysis/scripts')

from calculate_bull_bear_indicators import BullBearCalculator
from calculate_peer_comparison import PeerComparisonCalculator
from calculate_river_charts import RiverChartCalculator
import pymongo
from datetime import datetime
import time

class CompleteCalculationSystem:
    def __init__(self):
        self.db = pymongo.MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
        self.bull_bear = BullBearCalculator()
        self.peer_comparison = PeerComparisonCalculator()
        self.river_chart = RiverChartCalculator()
        
    def get_active_stocks(self, limit: int = None) -> list:
        """取得活躍股票清單"""
        # 從 stocks 取得所有股票（已整合 company_basic_info）
        stocks = list(self.db['stocks'].find(
            {},
            {'symbol': 1, 'name': 1, '_id': 0}
        ))
        
        stock_ids = [s.get('symbol', s.get('stock_id', '')) for s in stocks if s.get('symbol') or s.get('stock_id')]
        
        if limit:
            return stock_ids[:limit]
        return stock_ids
    
    def calculate_all(self, stock_ids: list = None, limit: int = 10):
        """
        執行所有計算
        
        參數:
            stock_ids: 股票代碼清單 (None = 使用活躍股票)
            limit: 處理股票數量限制
        """
        if stock_ids is None:
            stock_ids = self.get_active_stocks(limit)
        
        print("=" * 80)
        print("🚀 完整資料計算系統")
        print("=" * 80)
        print(f"處理股票: {len(stock_ids)} 支")
        print(f"計算項目: 多空指標、同業比較、河流圖")
        print("=" * 80)
        
        results = {
            'total': len(stock_ids),
            'success': 0,
            'failed': 0,
            'stocks': []
        }
        
        for idx, stock_id in enumerate(stock_ids, 1):
            print(f"\n[{idx}/{len(stock_ids)}] 處理 {stock_id}...")
            
            stock_result = {
                'stock_id': stock_id,
                'bull_bear': None,
                'peer_comparison': None,
                'river_chart': None,
                'status': 'processing'
            }
            
            try:
                # 1. 多空指標
                print(f"  ├─ 計算多空指標...", end='')
                try:
                    bull_bear = self.bull_bear.calculate_bull_bear_score(stock_id)
                    stock_result['bull_bear'] = {
                        'score': bull_bear['total_score'],
                        'signal': bull_bear['signal'],
                        'grade': bull_bear['grade']
                    }
                    # 儲存
                    self.db['bull_bear_indicators'].update_one(
                        {'stock_id': stock_id, 'date': bull_bear['date']},
                        {'$set': bull_bear},
                        upsert=True
                    )
                    print(f" ✅ {bull_bear['signal']}")
                except Exception as e:
                    print(f" ❌ {str(e)}")
                
                time.sleep(0.1)  # 避免過快
                
                # 2. 同業比較
                print(f"  ├─ 計算同業比較...", end='')
                try:
                    peer = self.peer_comparison.compare_with_peers(stock_id)
                    if 'error' not in peer:
                        stock_result['peer_comparison'] = {
                            'industry': peer.get('industry', '未知'),
                            'peer_count': peer.get('peer_count', 0)
                        }
                        # 儲存
                        self.db['peer_comparison'].update_one(
                            {'stock_id': stock_id},
                            {'$set': peer},
                            upsert=True
                        )
                        print(f" ✅ {peer.get('peer_count', 0)} 家同業")
                    else:
                        print(f" ⚠️ {peer['error']}")
                except Exception as e:
                    print(f" ❌ {str(e)}")
                
                time.sleep(0.1)
                
                # 3. 河流圖
                print(f"  └─ 計算河流圖...", end='')
                try:
                    river = self.river_chart.calculate_all_river_charts(stock_id, years=5)
                    
                    pe_ok = 'error' not in river['pe_river']
                    pb_ok = 'error' not in river['pb_river']
                    yield_ok = 'error' not in river['yield_river']
                    
                    stock_result['river_chart'] = {
                        'pe': pe_ok,
                        'pb': pb_ok,
                        'yield': yield_ok
                    }
                    
                    # 儲存
                    if pe_ok:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'PE'},
                            {'$set': river['pe_river']},
                            upsert=True
                        )
                    if pb_ok:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'PB'},
                            {'$set': river['pb_river']},
                            upsert=True
                        )
                    if yield_ok:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'YIELD'},
                            {'$set': river['yield_river']},
                            upsert=True
                        )
                    
                    count = sum([pe_ok, pb_ok, yield_ok])
                    print(f" ✅ {count}/3 圖表完成")
                except Exception as e:
                    print(f" ❌ {str(e)}")
                
                stock_result['status'] = 'success'
                results['success'] += 1
                
            except Exception as e:
                print(f"  ❌ 失敗: {str(e)}")
                stock_result['status'] = 'failed'
                stock_result['error'] = str(e)
                results['failed'] += 1
            
            results['stocks'].append(stock_result)
        
        # 統計報告
        print("\n" + "=" * 80)
        print("📊 執行結果統計")
        print("=" * 80)
        print(f"總計: {results['total']} 支")
        print(f"成功: {results['success']} 支 ({results['success']/results['total']*100:.1f}%)")
        print(f"失敗: {results['failed']} 支")
        
        # 資料庫統計
        print("\n" + "=" * 80)
        print("💾 資料庫統計")
        print("=" * 80)
        print(f"多空指標: {self.db['bull_bear_indicators'].count_documents({})} 筆")
        print(f"同業比較: {self.db['peer_comparison'].count_documents({})} 筆")
        print(f"河流圖: {self.db['river_charts'].count_documents({})} 筆")
        
        print("\n" + "=" * 80)
        print("✅ 所有計算完成!")
        print("=" * 80)
        
        return results


def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='完整資料計算系統')
    parser.add_argument('--stocks', nargs='+', help='指定股票代碼')
    parser.add_argument('--limit', type=int, default=10, help='處理股票數量限制')
    parser.add_argument('--all', action='store_true', help='處理所有股票')
    
    args = parser.parse_args()
    
    system = CompleteCalculationSystem()
    
    if args.stocks:
        # 指定股票
        system.calculate_all(stock_ids=args.stocks)
    elif args.all:
        # 所有股票
        system.calculate_all(stock_ids=None, limit=None)
    else:
        # 預設: 前N支
        system.calculate_all(limit=args.limit)


if __name__ == '__main__':
    main()
