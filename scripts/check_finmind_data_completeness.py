#!/usr/bin/env python3
"""
检查数据库数据完整性并使用 FinMind API 补齐

检查项目：
1. 必需字段完整性
2. FinMind 特有字段是否为默认值（需要补齐）
3. 数据范围是否完整
4. 价格数据一致性检查

Author: GitHub Copilot
Date: 2026-02-24
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
from bson.decimal128 import Decimal128
import requests
import time


def setup_logger(name: str) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


class DataCompletenessChecker:
    """数据完整性检查器"""
    
    # FinMind 标准字段
    FINMIND_FIELDS = {
        'required': {
            'stock_id', 'symbol', 'date', 'open', 'high', 'low', 'close', 
            'volume', 'updated_at'
        },
        'trading_info': {
            'Trading_Volume', 'Trading_money', 'Trading_turnover'
        },
        'price_derived': {
            'max', 'min', 'spread'
        },
        'optional': {
            'turnover', 'adjustment_factor', 'adj_close'
        }
    }
    
    def __init__(self, db_name: str = 'tw_stock_analysis'):
        """初始化检查器"""
        self.logger = setup_logger('DataCompletenessChecker')
        self.db_name = db_name
        
        # FinMind API 配置
        self.api_token = os.getenv('FINMIND_API_TOKEN')
        if not self.api_token:
            raise ValueError("请设置 FINMIND_API_TOKEN 环境变量")
        
        self.api_base = 'https://api.finmindtrade.com/api/v4/data'
        
        # 连接数据库
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        self.collection = self.db.stock_price
        
        self.logger.info(f"🔌 已连接到数据库: {db_name}")
    
    def check_field_completeness(self) -> Dict[str, Any]:
        """检查字段完整性"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("1️⃣ 字段完整性检查")
        self.logger.info("=" * 70)
        
        total_count = self.collection.count_documents({})
        results = {
            'total_records': total_count,
            'field_coverage': {},
            'issues': []
        }
        
        # 检查所有字段
        all_fields = set()
        for category, fields in self.FINMIND_FIELDS.items():
            all_fields.update(fields)
        
        for field in sorted(all_fields):
            count = self.collection.count_documents({field: {'$exists': True}})
            coverage = count / total_count * 100 if total_count > 0 else 0
            
            results['field_coverage'][field] = {
                'count': count,
                'coverage': coverage
            }
            
            status = "✅" if coverage == 100 else "⚠️"
            self.logger.info(f"  {status} {field}: {count:,}/{total_count:,} ({coverage:.1f}%)")
            
            if coverage < 100:
                results['issues'].append({
                    'field': field,
                    'missing_count': total_count - count
                })
        
        return results
    
    def check_default_values(self) -> Dict[str, Any]:
        """检查是否存在默认值（需要补齐真实数据）"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("2️⃣ 默认值检查（需要补齐）")
        self.logger.info("=" * 70)
        
        results = {
            'default_value_records': {},
            'needs_update': []
        }
        
        # 检查可能的默认值
        checks = [
            ('turnover', 0, '成交笔数'),
            ('Trading_turnover', 0, '交易笔数'),
            ('spread', 0, '涨跌幅'),
        ]
        
        for field, default_value, description in checks:
            count = self.collection.count_documents({field: default_value})
            total = self.collection.count_documents({field: {'$exists': True}})
            
            if count > 0:
                percentage = count / total * 100 if total > 0 else 0
                results['default_value_records'][field] = {
                    'count': count,
                    'total': total,
                    'percentage': percentage,
                    'description': description
                }
                
                status = "⚠️" if percentage > 10 else "ℹ️"
                self.logger.info(f"  {status} {description} ({field}): {count:,}/{total:,} ({percentage:.1f}%) 记录为默认值 {default_value}")
                
                if percentage > 10:
                    results['needs_update'].append(field)
        
        # 检查 Trading_money 是否合理（volume * close）
        pipeline = [
            {'$match': {'Trading_money': {'$exists': True}, 'volume': {'$gt': 0}}},
            {'$sample': {'size': 100}},
            {'$project': {
                'stock_id': 1,
                'date': 1,
                'volume': 1,
                'close': 1,
                'Trading_money': 1,
                'expected': {'$multiply': ['$volume', '$close']}
            }}
        ]
        
        sample = list(self.collection.aggregate(pipeline))
        mismatches = 0
        
        for doc in sample:
            actual = doc.get('Trading_money', 0)
            expected = doc.get('expected', 0)
            
            # 处理 Decimal128
            if isinstance(actual, Decimal128):
                actual = float(actual.to_decimal())
            if isinstance(expected, Decimal128):
                expected = float(expected.to_decimal())
            
            # 允许 5% 误差
            if abs(actual - expected) / max(expected, 1) > 0.05:
                mismatches += 1
        
        if mismatches > 10:
            self.logger.info(f"  ⚠️ Trading_money 数据异常: {mismatches}/100 样本不匹配")
            results['needs_update'].append('Trading_money')
        else:
            self.logger.info(f"  ✅ Trading_money 数据正常: {100 - mismatches}/100 样本正确")
        
        return results
    
    def check_data_range(self) -> Dict[str, Any]:
        """检查数据范围完整性"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("3️⃣ 数据范围检查")
        self.logger.info("=" * 70)
        
        results = {
            'stock_coverage': {},
            'date_gaps': []
        }
        
        # 获取所有股票
        all_stocks = self.collection.distinct('stock_id')
        self.logger.info(f"  涵盖股票数: {len(all_stocks)}")
        
        # 随机抽样 10 支股票检查数据连续性
        import random
        sample_stocks = random.sample(all_stocks, min(10, len(all_stocks)))
        
        self.logger.info(f"\n  抽样检查数据连续性 ({len(sample_stocks)} 支股票):")
        
        for stock_id in sample_stocks:
            records = list(self.collection.find(
                {'stock_id': stock_id},
                {'date': 1}
            ).sort('date', 1))
            
            if len(records) < 2:
                continue
            
            # 检查日期间隔
            gaps = []
            for i in range(1, len(records)):
                prev_date = records[i-1]['date']
                curr_date = records[i]['date']
                
                # 转换为 datetime
                if isinstance(prev_date, str):
                    prev_date = datetime.fromisoformat(prev_date)
                if isinstance(curr_date, str):
                    curr_date = datetime.fromisoformat(curr_date)
                
                delta = (curr_date - prev_date).days
                
                # 超过 7 天（考虑周末和假期）视为间隔
                if delta > 7:
                    gaps.append({
                        'start': prev_date,
                        'end': curr_date,
                        'days': delta
                    })
            
            if gaps:
                self.logger.info(f"    ⚠️ {stock_id}: 发现 {len(gaps)} 个数据间隔")
                results['date_gaps'].append({
                    'stock_id': stock_id,
                    'gaps': gaps
                })
            else:
                self.logger.info(f"    ✅ {stock_id}: 数据连续")
        
        return results
    
    def get_finmind_data(self, stock_id: str, start_date: str, end_date: str) -> Optional[List[Dict]]:
        """从 FinMind API 获取数据"""
        try:
            params = {
                'dataset': 'TaiwanStockPrice',
                'data_id': stock_id,
                'start_date': start_date,
                'end_date': end_date,
                'token': self.api_token
            }
            
            response = requests.get(self.api_base, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('msg') == 'success':
                    return data.get('data', [])
            
            return None
        
        except Exception as e:
            self.logger.error(f"  ❌ API 请求失败: {e}")
            return None
    
    def compare_with_finmind(self, stock_id: str = '2330', days: int = 7) -> Dict[str, Any]:
        """与 FinMind API 数据对比"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"4️⃣ 与 FinMind API 数据对比 (股票: {stock_id})")
        self.logger.info("=" * 70)
        
        # 获取最近的数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 从数据库获取
        db_records = list(self.collection.find(
            {
                'stock_id': stock_id,
                'date': {
                    '$gte': start_date,
                    '$lte': end_date
                }
            }
        ).sort('date', -1).limit(10))
        
        self.logger.info(f"  数据库记录数: {len(db_records)}")
        
        if not db_records:
            self.logger.warning(f"  ⚠️ 数据库无该股票数据")
            return {'status': 'no_data'}
        
        # 从 API 获取
        api_data = self.get_finmind_data(
            stock_id,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        if not api_data:
            self.logger.warning(f"  ⚠️ API 无数据返回")
            return {'status': 'api_failed'}
        
        self.logger.info(f"  FinMind API 记录数: {len(api_data)}")
        
        # 对比字段
        self.logger.info("\n  字段对比:")
        
        if db_records and api_data:
            db_fields = set(db_records[0].keys()) - {'_id'}
            api_fields = set(api_data[0].keys())
            
            missing_in_db = api_fields - db_fields
            extra_in_db = db_fields - api_fields
            
            if missing_in_db:
                self.logger.info(f"    ⚠️ 数据库缺少字段: {missing_in_db}")
            else:
                self.logger.info(f"    ✅ 数据库包含所有 API 字段")
            
            if extra_in_db:
                self.logger.info(f"    ℹ️ 数据库额外字段: {extra_in_db}")
            
            # 数据值对比（最近一条）
            if len(db_records) > 0 and len(api_data) > 0:
                self.logger.info("\n  最新数据值对比:")
                db_latest = db_records[0]
                
                # 找到相同日期的 API 数据
                db_date = db_latest.get('date')
                if isinstance(db_date, datetime):
                    db_date_str = db_date.strftime('%Y-%m-%d')
                else:
                    db_date_str = str(db_date)[:10]
                
                api_latest = None
                for record in api_data:
                    if record.get('date', '').startswith(db_date_str):
                        api_latest = record
                        break
                
                if api_latest:
                    compare_fields = ['open', 'high', 'low', 'close', 'volume']
                    for field in compare_fields:
                        db_val = db_latest.get(field)
                        api_val = api_latest.get(field)
                        
                        # 转换 Decimal128
                        if isinstance(db_val, Decimal128):
                            db_val = float(db_val.to_decimal())
                        
                        match = "✅" if abs(float(db_val) - float(api_val)) < 0.01 else "❌"
                        self.logger.info(f"    {match} {field}: DB={db_val}, API={api_val}")
        
        return {
            'status': 'success',
            'db_count': len(db_records),
            'api_count': len(api_data)
        }
    
    def generate_report(self) -> Dict[str, Any]:
        """生成完整报告"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("📊 数据完整性检查报告")
        self.logger.info("=" * 70)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'database': self.db_name,
            'checks': {}
        }
        
        # 1. 字段完整性
        report['checks']['field_completeness'] = self.check_field_completeness()
        
        # 2. 默认值检查
        report['checks']['default_values'] = self.check_default_values()
        
        # 3. 数据范围
        report['checks']['data_range'] = self.check_data_range()
        
        # 4. 与 API 对比
        report['checks']['api_comparison'] = self.compare_with_finmind('2330', 7)
        
        # 总结
        self.logger.info("\n" + "=" * 70)
        self.logger.info("📝 检查总结")
        self.logger.info("=" * 70)
        
        # 统计需要补齐的字段
        needs_update = report['checks']['default_values'].get('needs_update', [])
        missing_fields = [
            issue['field'] 
            for issue in report['checks']['field_completeness'].get('issues', [])
        ]
        
        if needs_update or missing_fields:
            self.logger.info("\n⚠️ 发现需要补齐的数据:")
            if missing_fields:
                self.logger.info(f"  - 缺失字段: {', '.join(missing_fields)}")
            if needs_update:
                self.logger.info(f"  - 需要更新: {', '.join(needs_update)}")
        else:
            self.logger.info("\n✅ 数据完整，无需补齐")
        
        return report
    
    def close(self):
        """关闭连接"""
        self.client.close()
        self.logger.info("\n✅ 数据库连接已关闭")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='检查数据库数据完整性')
    parser.add_argument('--stock-id', type=str, default='2330', help='对比的股票代码')
    parser.add_argument('--days', type=int, default=7, help='对比的天数')
    
    args = parser.parse_args()
    
    checker = DataCompletenessChecker()
    
    try:
        # 生成完整报告
        report = checker.generate_report()
        
        # 如果指定了股票，进行详细对比
        if args.stock_id != '2330':
            checker.compare_with_finmind(args.stock_id, args.days)
    
    finally:
        checker.close()


if __name__ == '__main__':
    main()
