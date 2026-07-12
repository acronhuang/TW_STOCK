"""
FinMind 數據驗證腳本

功能:
1. 驗證 MongoDB 中 FinMind 數據的完整性
2. 檢查數據覆蓋率、時間範圍、缺失值
3. 生成數據品質報告

執行:
    python3 scripts/validate_finmind_data.py

作者: Ming
創建日期: 2026-02-23
"""

import sys
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
from pymongo import MongoClient
import json


class FinMindDataValidator:
    """FinMind 數據驗證器"""
    
    def __init__(self, db_connection):
        """
        初始化
        
        Args:
            db_connection: MongoDB 連接
        """
        self.db = db_connection
        
        # 數據集配置
        self.datasets = {
            'stock_price': {
                'collection': 'stock_price',
                'required_fields': ['stock_id', 'date', 'open', 'high', 'low', 'close', 'volume'],
                'description': '股價日線數據'
            },
            'financial': {
                'collection': 'financial_reports',
                'required_fields': ['stock_id', 'date', 'revenue', 'net_income'],
                'description': '財務報表'
            },
            'holdings': {
                'collection': 'institutional_holdings',
                'required_fields': ['stock_id', 'date', 'level', 'percent'],
                'description': '大戶持股'
            },
            'per': {
                'collection': 'taiwan_stock_per',
                'required_fields': ['stock_id', 'date', 'value'],
                'description': '本益比'
            },
            'dividend': {
                'collection': 'dividend',
                'required_fields': ['stock_id', 'date', 'dividend_type', 'dividend_value'],
                'description': '除權息'
            },
            'institutional_trading': {
                'collection': 'institutional_trading',
                'required_fields': ['stock_id', 'date'],
                'description': '法人買賣超'
            }
        }
    
    def validate_dataset(self, dataset_key: str) -> Dict:
        """
        驗證單一數據集
        
        Args:
            dataset_key: 數據集鍵值
        
        Returns:
            驗證結果
        """
        print(f"\n{'='*80}")
        print(f"驗證數據集: {dataset_key}")
        print(f"{'='*80}")
        
        config = self.datasets[dataset_key]
        collection = self.db[config['collection']]
        
        # 1. 總記錄數
        total_records = collection.count_documents({})
        print(f"✓ 總記錄數: {total_records:,}")
        
        # 2. 涵蓋股票數
        stock_count = len(collection.distinct('stock_id'))
        print(f"✓ 涵蓋股票數: {stock_count:,}")
        
        # 3. 時間範圍
        earliest_date = collection.find_one(sort=[('date', 1)])
        latest_date = collection.find_one(sort=[('date', -1)])
        
        if earliest_date and latest_date:
            print(f"✓ 時間範圍: {earliest_date['date']} ~ {latest_date['date']}")
            date_range = {
                'earliest': earliest_date['date'],
                'latest': latest_date['date']
            }
        else:
            print(f"⚠️  無法獲取時間範圍")
            date_range = None
        
        # 4. 欄位完整性
        missing_fields = {}
        for field in config['required_fields']:
            missing_count = collection.count_documents({field: {'$exists': False}})
            if missing_count > 0:
                missing_fields[field] = missing_count
                print(f"⚠️  欄位 {field} 缺失: {missing_count:,} 筆")
            else:
                print(f"✓ 欄位 {field}: 完整")
        
        # 5. 資料完整性（按股票統計）
        pipeline = [
            {'$group': {
                '_id': '$stock_id',
                'count': {'$sum': 1},
                'dates': {'$addToSet': '$date'}
            }},
            {'$project': {
                'stock_id': '$_id',
                'count': 1,
                'date_count': {'$size': '$dates'}
            }}
        ]
        
        stock_stats = list(collection.aggregate(pipeline))
        
        if stock_stats:
            avg_records_per_stock = sum(s['count'] for s in stock_stats) / len(stock_stats)
            print(f"✓ 平均每支股票記錄數: {avg_records_per_stock:.0f}")
        else:
            avg_records_per_stock = 0
        
        # 6. 數據品質評分
        quality_score = self._calculate_quality_score(
            total_records,
            stock_count,
            missing_fields,
            avg_records_per_stock
        )
        
        print(f"\n數據品質評分: {quality_score:.1f}/100")
        
        result = {
            'dataset': dataset_key,
            'description': config['description'],
            'total_records': total_records,
            'stock_count': stock_count,
            'date_range': date_range,
            'missing_fields': missing_fields,
            'avg_records_per_stock': avg_records_per_stock,
            'quality_score': quality_score
        }
        
        return result
    
    def _calculate_quality_score(
        self,
        total_records: int,
        stock_count: int,
        missing_fields: Dict,
        avg_records_per_stock: float
    ) -> float:
        """
        計算數據品質評分
        
        Args:
            total_records: 總記錄數
            stock_count: 股票數
            missing_fields: 缺失欄位統計
            avg_records_per_stock: 平均記錄數
        
        Returns:
            品質評分（0-100）
        """
        score = 100.0
        
        # 記錄數不足 -> 扣分
        if total_records < 100_000:
            score -= 30
        elif total_records < 500_000:
            score -= 15
        
        # 股票覆蓋率不足 -> 扣分
        if stock_count < 1000:
            score -= 20
        elif stock_count < 2000:
            score -= 10
        
        # 有缺失欄位 -> 扣分
        if missing_fields:
            score -= len(missing_fields) * 10
        
        # 平均記錄數不足 -> 扣分
        if avg_records_per_stock < 100:
            score -= 15
        elif avg_records_per_stock < 500:
            score -= 5
        
        return max(score, 0)
    
    def validate_all_datasets(self) -> List[Dict]:
        """
        驗證所有數據集
        
        Returns:
            驗證結果列表
        """
        results = []
        
        for dataset_key in self.datasets.keys():
            try:
                result = self.validate_dataset(dataset_key)
                results.append(result)
            except Exception as e:
                print(f"⚠️  驗證 {dataset_key} 失敗: {e}")
                results.append({
                    'dataset': dataset_key,
                    'error': str(e)
                })
        
        return results
    
    def generate_report(self, results: List[Dict], output_file: str):
        """
        生成驗證報告
        
        Args:
            results: 驗證結果
            output_file: 輸出檔案路徑
        """
        print(f"\n{'='*80}")
        print(f"數據品質總結")
        print(f"{'='*80}\n")
        
        # 計算總體指標
        total_records = sum(r.get('total_records', 0) for r in results)
        avg_quality_score = sum(r.get('quality_score', 0) for r in results) / len(results)
        
        print(f"總記錄數: {total_records:,}")
        print(f"平均品質評分: {avg_quality_score:.1f}/100\n")
        
        # 按數據集顯示
        print(f"{'數據集':<30} {'記錄數':>15} {'股票數':>10} {'品質評分':>12}")
        print(f"{'-'*80}")
        
        for r in results:
            if 'error' in r:
                print(f"{r['dataset']:<30} {'ERROR':>15} {'':>10} {'':>12}")
            else:
                print(f"{r['description']:<30} {r['total_records']:>15,} "
                      f"{r['stock_count']:>10,} {r['quality_score']:>12.1f}")
        
        # 儲存 JSON
        report_data = {
            'validation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_records': total_records,
                'avg_quality_score': avg_quality_score
            },
            'datasets': results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"\n✓ 驗證報告已儲存: {output_file}")
    
    def check_data_consistency(self) -> Dict:
        """
        檢查數據一致性
        
        檢查項目:
        1. stock_price 與 per 的股票列表是否一致
        2. 時間範圍是否對齊
        3. 股票代碼格式是否統一
        
        Returns:
            一致性檢查結果
        """
        print(f"\n{'='*80}")
        print(f"數據一致性檢查")
        print(f"{'='*80}\n")
        
        # 1. 股票列表一致性
        stock_ids_price = set(self.db['stock_price'].distinct('stock_id'))
        stock_ids_per = set(self.db['taiwan_stock_per'].distinct('stock_id'))
        
        common_stocks = stock_ids_price & stock_ids_per
        only_in_price = stock_ids_price - stock_ids_per
        only_in_per = stock_ids_per - stock_ids_price
        
        print(f"✓ stock_price 股票數: {len(stock_ids_price):,}")
        print(f"✓ taiwan_stock_per 股票數: {len(stock_ids_per):,}")
        print(f"✓ 共同股票數: {len(common_stocks):,}")
        
        if only_in_price:
            print(f"⚠️  僅在 stock_price: {len(only_in_price):,} 支")
        
        if only_in_per:
            print(f"⚠️  僅在 taiwan_stock_per: {len(only_in_per):,} 支")
        
        # 2. 時間範圍對齊
        price_latest = self.db['stock_price'].find_one(sort=[('date', -1)])
        per_latest = self.db['taiwan_stock_per'].find_one(sort=[('date', -1)])
        
        print(f"\n✓ stock_price 最新日期: {price_latest['date'] if price_latest else 'N/A'}")
        print(f"✓ taiwan_stock_per 最新日期: {per_latest['date'] if per_latest else 'N/A'}")
        
        # 3. 檢查股票代碼格式
        invalid_stock_ids = []
        for stock_id in list(stock_ids_price)[:100]:  # 抽樣檢查
            if not (stock_id.isdigit() and len(stock_id) == 4):
                invalid_stock_ids.append(stock_id)
        
        if invalid_stock_ids:
            print(f"\n⚠️  發現無效股票代碼: {invalid_stock_ids[:10]}")
        else:
            print(f"\n✓ 股票代碼格式正確")
        
        result = {
            'stock_list_match': len(common_stocks) / max(len(stock_ids_price), len(stock_ids_per)),
            'only_in_price': len(only_in_price),
            'only_in_per': len(only_in_per),
            'invalid_stock_ids': invalid_stock_ids
        }
        
        return result


def main():
    """主函數"""
    print(f"\n{'='*80}")
    print(f"FinMind 數據驗證")
    print(f"{'='*80}\n")
    
    # 連接資料庫
    print("連接 MongoDB...")
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    print("✓ 連接成功\n")
    
    # 初始化驗證器
    validator = FinMindDataValidator(db)
    
    # 驗證所有數據集
    results = validator.validate_all_datasets()
    
    # 檢查一致性
    consistency = validator.check_data_consistency()
    
    # 生成報告
    output_file = f"finmind_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    validator.generate_report(results, output_file)


if __name__ == "__main__":
    main()
