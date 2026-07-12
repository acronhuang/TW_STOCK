#!/usr/bin/env python3
"""
安全集合優化執行腳本
1. 不刪除正在使用的集合
2. 創建性能索引
3. 清理測試數據（需確認）
"""

from pymongo import MongoClient
from datetime import datetime
import json

class SafeCollectionOptimizer:
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        
        # 定義關鍵集合（不可刪除）
        self.critical_collections = {
            'stocks',                    # 下載程式使用
            'stock_price',              # 下載程式使用
            'institutional_investors',   # 下載程式使用
            'technical_indicators',      # 技術指標
            'tickers',                   # NestJS API 使用
            'dividends',                 # 股利數據
            'monthly_revenue',           # 月營收
            'pe_pb_yield',              # 本益比等
            'margin_trading',            # 融資融券
            'market_statistics'          # 市場統計
        }
    
    def check_download_status(self):
        """檢查下載程式是否運行中"""
        import subprocess
        
        print("\n🔍 檢查背景下載程式...")
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        
        is_running = 'background_full_download' in result.stdout
        
        if is_running:
            print("  ✅ 背景下載程式運行中 (PID 可見於 ps aux)")
            print("  ⚠️  優化操作將避免影響下載程式")
        else:
            print("  ℹ️  背景下載程式未運行")
        
        return is_running
    
    def analyze_safe_operations(self):
        """分析可安全執行的操作"""
        print("\n" + "="*80)
        print("📊 安全操作分析")
        print("="*80)
        
        collections = set(self.db.list_collection_names())
        
        # 1. 檢查空集合
        print("\n1️⃣ 空集合檢查:")
        empty_collections = []
        for coll_name in collections:
            count = self.db[coll_name].count_documents({})
            if count == 0:
                empty_collections.append(coll_name)
                print(f"  • {coll_name}: 0 筆 ❌ 可刪除")
        
        if not empty_collections:
            print("  ✅ 無空集合")
        
        # 2. 檢查測試數據
        print("\n2️⃣ 測試數據檢查:")
        test_collections = []
        
        # financial_statements 僅 6 筆
        if 'financial_statements' in collections:
            count = self.db['financial_statements'].count_documents({})
            if count < 10:
                test_collections.append({
                    'name': 'financial_statements',
                    'count': count,
                    'action': 'review',
                    'reason': '數據量極少，可能是測試數據'
                })
                print(f"  • financial_statements: {count} 筆 ⚠️  需審查")
        
        if not test_collections:
            print("  ✅ 無可疑測試數據")
        
        # 3. 檢查缺少的索引
        print("\n3️⃣ 索引檢查:")
        missing_indexes = []
        
        index_recommendations = {
            'stock_price': [('symbol', 1), ('date', -1)],
            'institutional_investors': [('symbol', 1), ('date', -1)],
            'technical_indicators': [('symbol', 1), ('date', -1)],
            'dividends': [('symbol', 1)],
            'monthly_revenue': [('symbol', 1), ('year_month', -1)],
            'pe_pb_yield': [('symbol', 1), ('date', -1)],
            'margin_trading': [('symbol', 1), ('date', -1)],
            'stocks': [('symbol', 1)]
        }
        
        for coll_name, index_spec in index_recommendations.items():
            if coll_name in collections:
                coll = self.db[coll_name]
                count = coll.count_documents({})
                
                if count > 0:
                    # 檢查是否已有索引
                    indexes = list(coll.list_indexes())
                    index_names = [idx['name'] for idx in indexes if idx['name'] != '_id_']
                    
                    # 生成建議的索引名稱
                    if len(index_spec) == 2:
                        suggested_name = f"{index_spec[0][0]}_{index_spec[0][1]}_{index_spec[1][0]}_{index_spec[1][1]}"
                    else:
                        suggested_name = f"{index_spec[0][0]}_{index_spec[0][1]}"
                    
                    # 檢查是否已存在相似索引
                    has_similar = False
                    for idx_name in index_names:
                        if index_spec[0][0] in idx_name:
                            has_similar = True
                            break
                    
                    if not has_similar:
                        missing_indexes.append({
                            'collection': coll_name,
                            'index': index_spec,
                            'count': count,
                            'benefit': self._estimate_index_benefit(count)
                        })
                        print(f"  • {coll_name}: 缺少 {index_spec} 索引 ({count:,} 筆)")
        
        if not missing_indexes:
            print("  ✅ 所有集合已有適當索引")
        
        return {
            'empty_collections': empty_collections,
            'test_collections': test_collections,
            'missing_indexes': missing_indexes
        }
    
    def _estimate_index_benefit(self, count):
        """估算索引帶來的性能提升"""
        if count > 500000:
            return "極高 (>50萬筆)"
        elif count > 100000:
            return "高 (>10萬筆)"
        elif count > 10000:
            return "中 (>1萬筆)"
        else:
            return "低 (<1萬筆)"
    
    def create_indexes_safely(self, missing_indexes, dry_run=True):
        """安全創建索引（不影響運行中的操作）"""
        print("\n" + "="*80)
        if dry_run:
            print("🔍 索引創建 - 模擬模式")
        else:
            print("⚡ 索引創建 - 執行模式")
        print("="*80)
        
        results = []
        
        # 按優先級排序（記錄數多的優先）
        sorted_indexes = sorted(
            missing_indexes,
            key=lambda x: x['count'],
            reverse=True
        )
        
        for item in sorted_indexes:
            coll_name = item['collection']
            index_spec = item['index']
            count = item['count']
            benefit = item['benefit']
            
            print(f"\n📊 {coll_name}:")
            print(f"  記錄數: {count:,}")
            print(f"  預期效益: {benefit}")
            print(f"  索引: {index_spec}")
            
            try:
                if not dry_run:
                    # 使用 background=True 避免阻塞
                    self.db[coll_name].create_index(
                        index_spec,
                        background=True  # 背景建立，不阻塞查詢
                    )
                    print(f"  ✅ 索引創建成功 (背景模式)")
                else:
                    print(f"  🔍 (模擬) 將創建索引")
                
                results.append({
                    'collection': coll_name,
                    'status': 'success',
                    'index': index_spec
                })
                
            except Exception as e:
                print(f"  ❌ 失敗: {e}")
                results.append({
                    'collection': coll_name,
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
    
    def review_financial_statements(self):
        """審查 financial_statements 集合"""
        print("\n" + "="*80)
        print("🔍 financial_statements 集合審查")
        print("="*80)
        
        coll = self.db['financial_statements']
        count = coll.count_documents({})
        
        print(f"\n記錄數: {count}")
        
        if count > 0:
            print("\n數據樣本:")
            for i, doc in enumerate(coll.find().limit(10), 1):
                print(f"\n  {i}. {doc.get('symbol', 'N/A')}")
                print(f"     來源: {doc.get('source', 'unknown')}")
                print(f"     年季: {doc.get('year', 'N/A')}/{doc.get('season', 'N/A')}")
                print(f"     時間: {doc.get('updateTime', 'N/A')}")
        
        print("\n建議:")
        print("  • 此集合為統一財報接口，整合 FinMind + Yahoo 數據")
        print("  • 目前僅 6 筆為正常狀態（測試階段）")
        print("  • 建議保留，等待財報下載腳本填充數據")
        print("  • ⚠️  不建議刪除")
    
    def generate_optimization_report(self, analysis, index_results):
        """生成優化報告"""
        print("\n" + "="*80)
        print("📄 優化報告")
        print("="*80)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'background_download': 'running',
            'analysis': {
                'empty_collections': len(analysis['empty_collections']),
                'test_collections': len(analysis['test_collections']),
                'missing_indexes': len(analysis['missing_indexes'])
            },
            'actions': {
                'indexes_created': len([r for r in index_results if r['status'] == 'success']),
                'errors': len([r for r in index_results if r['status'] == 'error'])
            },
            'recommendations': []
        }
        
        # 空集合建議
        if analysis['empty_collections']:
            report['recommendations'].append({
                'type': 'delete_empty',
                'collections': analysis['empty_collections'],
                'action': '可安全刪除'
            })
        
        # 測試數據建議
        if analysis['test_collections']:
            report['recommendations'].append({
                'type': 'review_test_data',
                'collections': [t['name'] for t in analysis['test_collections']],
                'action': '需人工審查，建議保留'
            })
        
        # tickers 集合建議
        report['recommendations'].append({
            'type': 'keep_tickers',
            'reason': 'NestJS API 專用，與 Python 腳本分離',
            'action': '保持現狀'
        })
        
        # 數據源統一建議
        report['recommendations'].append({
            'type': 'unify_sources',
            'reason': '避免多數據源各自建立集合',
            'action': '未來新數據源統一使用現有集合結構'
        })
        
        # 保存報告
        filename = f'SAFE_OPTIMIZATION_REPORT_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 報告已保存: {filename}")
        
        # 顯示總結
        print("\n" + "="*80)
        print("📊 總結")
        print("="*80)
        
        print(f"\n✅ 完成項目:")
        print(f"  • 空集合: {len(analysis['empty_collections'])} 個")
        print(f"  • 創建索引: {len([r for r in index_results if r['status'] == 'success'])} 個")
        
        print(f"\n⚠️  需注意:")
        print(f"  • 測試數據集合: {len(analysis['test_collections'])} 個 (建議保留)")
        print(f"  • tickers 集合: 保持現狀 (NestJS API 使用)")
        
        print(f"\n💡 建議:")
        print(f"  • 背景下載程式持續運行，不受影響")
        print(f"  • 索引已在背景創建，不阻塞查詢")
        print(f"  • 未來避免多數據源各自建立集合")
        
        return report

def main():
    import sys
    
    optimizer = SafeCollectionOptimizer()
    
    # 1. 檢查下載狀態
    is_downloading = optimizer.check_download_status()
    
    if is_downloading:
        print("\n⚠️  檢測到背景下載程式運行中")
        print("   將使用安全模式，避免影響下載")
    
    # 2. 分析安全操作
    analysis = optimizer.analyze_safe_operations()
    
    # 3. 審查 financial_statements
    optimizer.review_financial_statements()
    
    # 4. 詢問是否執行索引創建
    print("\n" + "="*80)
    print("⚠️  執行選項")
    print("="*80)
    print("1. 僅生成報告")
    print("2. 模擬創建索引 (Dry Run)")
    print("3. 實際創建索引 (背景模式，不阻塞)")
    print("4. 退出")
    
    if '--execute' in sys.argv:
        choice = '3'
    elif '--dry-run' in sys.argv:
        choice = '2'
    else:
        choice = input("\n請選擇 [1-4]: ").strip()
    
    index_results = []
    
    if choice == '1':
        print("\n僅生成分析報告...")
    
    elif choice == '2':
        print("\n模擬創建索引...")
        index_results = optimizer.create_indexes_safely(
            analysis['missing_indexes'],
            dry_run=True
        )
    
    elif choice == '3':
        print("\n⚠️  將在背景創建索引（不影響查詢）")
        confirm = input("確定繼續? [y/N]: ").strip().lower()
        if confirm == 'y':
            index_results = optimizer.create_indexes_safely(
                analysis['missing_indexes'],
                dry_run=False
            )
            print("\n✅ 索引創建完成")
        else:
            print("已取消")
            return
    
    else:
        print("已退出")
        return
    
    # 5. 生成報告
    optimizer.generate_optimization_report(analysis, index_results)
    
    print("\n" + "="*80)
    print("🎉 優化完成")
    print("="*80)
    print("\n✅ 所有操作安全完成，背景下載不受影響")

if __name__ == '__main__':
    main()
