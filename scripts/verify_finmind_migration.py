#!/usr/bin/env python3
"""
数据迁移验证脚本

验证内容：
1. 所有记录都有 stock_id 字段
2. 字段名称符合 FinMind 标准
3. 数据完整性检查
4. 数据抽样对比

Author: GitHub Copilot
Date: 2026-02-24
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import random
import pymongo
from pymongo import MongoClient
from bson.decimal128 import Decimal128


def setup_logger(name: str) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 控制台处理器
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


class MigrationVerifier:
    """迁移验证工具"""
    
    # FinMind 必需字段
    REQUIRED_FIELDS = {
        'stock_id',
        'symbol',
        'date',
        'open',
        'high',
        'low',
        'close',
        'volume',
        'updated_at'
    }
    
    # FinMind 标准字段（可选）
    OPTIONAL_FIELDS = {
        'max',
        'min',
        'spread',
        'turnover',
        'Trading_Volume',
        'Trading_money',
        'Trading_turnover',
        'adjustment_factor',
        'adj_close'
    }
    
    # 禁止字段（不应存在）
    FORBIDDEN_FIELDS = {
        'source',          # 旧数据源标识
        'updateTime'       # 旧时间字段
    }
    
    def __init__(self, db_name: str = 'tw_stock_analysis'):
        """初始化验证器"""
        self.logger = setup_logger('MigrationVerifier')
        self.db_name = db_name
        
        # 连接数据库
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        self.collection = self.db.stock_price
        
        self.logger.info(f"🔌 已连接到数据库: {db_name}")
    
    def verify_all(self) -> Dict[str, Any]:
        """执行所有验证"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("🔍 数据迁移验证报告")
        self.logger.info("=" * 70)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'database': self.db_name,
            'collection': 'stock_price',
            'checks': {}
        }
        
        # 1. 基础统计
        results['checks']['basic_stats'] = self.check_basic_stats()
        
        # 2. 必需字段检查
        results['checks']['required_fields'] = self.check_required_fields()
        
        # 3. 禁止字段检查
        results['checks']['forbidden_fields'] = self.check_forbidden_fields()
        
        # 4. stock_id 完整性检查
        results['checks']['stock_id_integrity'] = self.check_stock_id_integrity()
        
        # 5. 数据类型检查
        results['checks']['data_types'] = self.check_data_types()
        
        # 6. 数据抽样检查
        results['checks']['sampling'] = self.sample_check(sample_size=10)
        
        # 总结
        self.print_summary(results)
        
        return results
    
    def check_basic_stats(self) -> Dict[str, Any]:
        """基础统计"""
        self.logger.info("\n1️⃣ 基础统计")
        
        total_count = self.collection.count_documents({})
        stock_count = len(self.collection.distinct('stock_id'))
        
        # 日期范围
        earliest = self.collection.find_one({}, {'date': 1}, sort=[('date', 1)])
        latest = self.collection.find_one({}, {'date': 1}, sort=[('date', -1)])
        
        stats = {
            'total_records': total_count,
            'unique_stocks': stock_count,
            'date_range': {
                'earliest': earliest['date'] if earliest else None,
                'latest': latest['date'] if latest else None
            }
        }
        
        self.logger.info(f"  总记录数: {total_count:,}")
        self.logger.info(f"  涵盖股票数: {stock_count}")
        if earliest and latest:
            # 处理不同日期格式
            earliest_date = earliest['date'] if isinstance(earliest['date'], str) else earliest['date'].date()
            latest_date = latest['date'] if isinstance(latest['date'], str) else latest['date'].date()
            self.logger.info(f"  日期范围: {earliest_date} ~ {latest_date}")
        
        return stats
    
    def check_required_fields(self) -> Dict[str, Any]:
        """检查必需字段"""
        self.logger.info("\n2️⃣ 必需字段检查")
        
        results = {}
        all_passed = True
        
        for field in self.REQUIRED_FIELDS:
            count_with_field = self.collection.count_documents({field: {'$exists': True}})
            total_count = self.collection.count_documents({})
            
            passed = (count_with_field == total_count)
            all_passed = all_passed and passed
            
            results[field] = {
                'count': count_with_field,
                'total': total_count,
                'passed': passed
            }
            
            status = "✅" if passed else "❌"
            self.logger.info(f"  {status} {field}: {count_with_field:,}/{total_count:,}")
        
        results['all_passed'] = all_passed
        return results
    
    def check_forbidden_fields(self) -> Dict[str, Any]:
        """检查禁止字段"""
        self.logger.info("\n3️⃣ 禁止字段检查")
        
        results = {}
        all_passed = True
        
        for field in self.FORBIDDEN_FIELDS:
            count_with_field = self.collection.count_documents({field: {'$exists': True}})
            
            passed = (count_with_field == 0)
            all_passed = all_passed and passed
            
            results[field] = {
                'count': count_with_field,
                'passed': passed
            }
            
            status = "✅" if passed else "❌"
            self.logger.info(f"  {status} {field}: {count_with_field:,} 条记录")
        
        results['all_passed'] = all_passed
        return results
    
    def check_stock_id_integrity(self) -> Dict[str, Any]:
        """检查 stock_id 完整性"""
        self.logger.info("\n4️⃣ stock_id 完整性检查")
        
        # 检查 stock_id 为 null 的记录
        null_count = self.collection.count_documents({'stock_id': None})
        
        # 检查 stock_id 与 symbol 不一致的记录
        pipeline = [
            {
                '$match': {
                    'stock_id': {'$ne': None},
                    '$expr': {'$ne': ['$stock_id', '$symbol']}
                }
            },
            {'$count': 'mismatch_count'}
        ]
        mismatch_result = list(self.collection.aggregate(pipeline))
        mismatch_count = mismatch_result[0]['mismatch_count'] if mismatch_result else 0
        
        results = {
            'null_stock_id': null_count,
            'mismatch_with_symbol': mismatch_count,
            'passed': (null_count == 0 and mismatch_count == 0)
        }
        
        status = "✅" if results['passed'] else "❌"
        self.logger.info(f"  {status} stock_id 为 null: {null_count:,} 条")
        self.logger.info(f"  {status} stock_id 与 symbol 不一致: {mismatch_count:,} 条")
        
        return results
    
    def check_data_types(self) -> Dict[str, Any]:
        """检查数据类型"""
        self.logger.info("\n5️⃣ 数据类型检查")
        
        # 抽样检查
        sample = self.collection.find_one({'stock_id': {'$ne': None}})
        
        if not sample:
            self.logger.error("  ❌ 无法获取样本数据")
            return {'passed': False, 'error': '无样本数据'}
        
        results = {}
        type_checks = {
            'stock_id': str,
            'symbol': str,
            'date': datetime,
            'open': (float, Decimal128, int),
            'high': (float, Decimal128, int),
            'low': (float, Decimal128, int),
            'close': (float, Decimal128, int),
            'volume': (float, Decimal128, int),
            'updated_at': datetime
        }
        
        all_passed = True
        for field, expected_type in type_checks.items():
            if field in sample:
                actual_value = sample[field]
                if isinstance(expected_type, tuple):
                    passed = isinstance(actual_value, expected_type)
                    type_name = ' or '.join(t.__name__ for t in expected_type)
                else:
                    passed = isinstance(actual_value, expected_type)
                    type_name = expected_type.__name__
                
                all_passed = all_passed and passed
                
                status = "✅" if passed else "❌"
                actual_type = type(actual_value).__name__
                self.logger.info(f"  {status} {field}: {actual_type} (期望: {type_name})")
                
                results[field] = {
                    'expected': type_name,
                    'actual': actual_type,
                    'passed': passed
                }
        
        results['all_passed'] = all_passed
        return results
    
    def sample_check(self, sample_size: int = 10) -> Dict[str, Any]:
        """数据抽样检查"""
        self.logger.info(f"\n6️⃣ 数据抽样检查 (样本数: {sample_size})")
        
        # 随机抽取股票
        all_stock_ids = self.collection.distinct('stock_id', {'stock_id': {'$ne': None}})
        sample_stock_ids = random.sample(all_stock_ids, min(sample_size, len(all_stock_ids)))
        
        results = []
        
        for stock_id in sample_stock_ids:
            # 获取该股票的记录数和日期范围
            count = self.collection.count_documents({'stock_id': stock_id})
            earliest = self.collection.find_one(
                {'stock_id': stock_id},
                {'date': 1, 'close': 1},
                sort=[('date', 1)]
            )
            latest = self.collection.find_one(
                {'stock_id': stock_id},
                {'date': 1, 'close': 1},
                sort=[('date', -1)]
            )
            
            record_info = {
                'stock_id': stock_id,
                'record_count': count,
                'date_range': {
                    'earliest': earliest['date'] if earliest else None,
                    'latest': latest['date'] if latest else None
                },
                'price_sample': {
                    'earliest_close': float(earliest['close'].to_decimal()) if earliest and isinstance(earliest['close'], Decimal128) else None,
                    'latest_close': float(latest['close'].to_decimal()) if latest and isinstance(latest['close'], Decimal128) else None
                }
            }
            
            results.append(record_info)
            
            self.logger.info(f"  📊 {stock_id}: {count:,} 條記錄")
            if earliest and latest:
                self.logger.info(f"     日期: {earliest['date'].date()} ~ {latest['date'].date()}")
        
        return {
            'sample_size': len(results),
            'samples': results
        }
    
    def print_summary(self, results: Dict[str, Any]):
        """打印验证总结"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("📝 验证总结")
        self.logger.info("=" * 70)
        
        checks = results['checks']
        
        # 统计通过的检查
        passed_checks = []
        failed_checks = []
        
        for check_name, check_result in checks.items():
            if check_name in ('basic_stats', 'sampling'):
                continue  # 跳过统计信息和抽样检查
            
            if isinstance(check_result, dict):
                if check_result.get('passed') or check_result.get('all_passed'):
                    passed_checks.append(check_name)
                else:
                    failed_checks.append(check_name)
        
        total_checks = len(passed_checks) + len(failed_checks)
        self.logger.info(f"\n通过检查: {len(passed_checks)}/{total_checks}")
        
        if failed_checks:
            self.logger.error(f"\n❌ 失败的检查:")
            for check in failed_checks:
                self.logger.error(f"   - {check}")
        else:
            self.logger.info("\n✅ 所有检查通过！数据迁移成功！")
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    verifier = MigrationVerifier()
    
    try:
        results = verifier.verify_all()
        
        # 判断是否通过
        all_passed = all(
            check.get('passed') or check.get('all_passed')
            for check_name, check in results['checks'].items()
            if check_name != 'basic_stats' and isinstance(check, dict)
        )
        
        if not all_passed:
            sys.exit(1)
    
    finally:
        verifier.close()


if __name__ == '__main__':
    main()
