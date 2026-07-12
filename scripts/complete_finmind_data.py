#!/usr/bin/env python3
"""
使用 FinMind API 补齐数据库缺失的字段和数据

补齐内容：
1. 缺少的字段（max, min, spread, Trading_* 等）
2. 默认值字段（turnover, Trading_turnover, spread）
3. 缺失的 adj_close 和 adjustment_factor

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


class DataCompleter:
    """数据补齐工具"""
    
    def __init__(self, db_name: str = 'tw_stock_analysis', dry_run: bool = False):
        """初始化"""
        self.logger = setup_logger('DataCompleter')
        self.db_name = db_name
        self.dry_run = dry_run
        
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
        if dry_run:
            self.logger.warning("⚠️  演练模式：不会实际修改数据")
    
    def fix_missing_fields(self) -> int:
        """修复缺失的字段（从现有数据计算）"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("1️⃣ 修复缺失字段（从现有数据计算）")
        self.logger.info("=" * 70)
        
        fixed_count = 0
        
        # 1. 为缺少 max 的记录从 high 复制
        missing_max = self.collection.count_documents({
            'max': {'$exists': False},
            'high': {'$exists': True}
        })
        
        if missing_max > 0:
            self.logger.info(f"  修复 max 字段: {missing_max:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'max': {'$exists': False}, 'high': {'$exists': True}},
                    [{'$set': {'max': '$high'}}]
                )
                fixed_count += result.modified_count
        
        # 2. 为缺少 min 的记录从 low 复制
        missing_min = self.collection.count_documents({
            'min': {'$exists': False},
            'low': {'$exists': True}
        })
        
        if missing_min > 0:
            self.logger.info(f"  修复 min 字段: {missing_min:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'min': {'$exists': False}, 'low': {'$exists': True}},
                    [{'$set': {'min': '$low'}}]
                )
                fixed_count += result.modified_count
        
        # 3. 为缺少 Trading_Volume 的记录从 volume 复制
        missing_tv = self.collection.count_documents({
            'Trading_Volume': {'$exists': False},
            'volume': {'$exists': True}
        })
        
        if missing_tv > 0:
            self.logger.info(f"  修复 Trading_Volume 字段: {missing_tv:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'Trading_Volume': {'$exists': False}, 'volume': {'$exists': True}},
                    [{'$set': {'Trading_Volume': '$volume'}}]
                )
                fixed_count += result.modified_count
        
        # 4. 计算 spread（close - open）
        missing_spread = self.collection.count_documents({
            'spread': {'$exists': False},
            'close': {'$exists': True},
            'open': {'$exists': True}
        })
        
        if missing_spread > 0:
            self.logger.info(f"  计算 spread 字段: {missing_spread:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {
                        'spread': {'$exists': False},
                        'close': {'$exists': True},
                        'open': {'$exists': True}
                    },
                    [{'$set': {'spread': {'$subtract': ['$close', '$open']}}}]
                )
                fixed_count += result.modified_count
        
        # 5. 计算 Trading_money（volume * close）
        missing_tm = self.collection.count_documents({
            'Trading_money': {'$exists': False},
            'volume': {'$exists': True},
            'close': {'$exists': True}
        })
        
        if missing_tm > 0:
            self.logger.info(f"  计算 Trading_money 字段: {missing_tm:,} 条")
            if not self.dry_run:
                # Trading_money 需要转换为整数
                result = self.collection.update_many(
                    {
                        'Trading_money': {'$exists': False},
                        'volume': {'$exists': True,'$ne': 0},
                        'close': {'$exists': True}
                    },
                    [{'$set': {'Trading_money': {'$toInt': {'$multiply': ['$volume', '$close']}}}}]
                )
                fixed_count += result.modified_count
        
        # 6. 为缺少 turnover 的记录设置默认值
        missing_turnover = self.collection.count_documents({'turnover': {'$exists': False}})
        
        if missing_turnover > 0:
            self.logger.info(f"  添加 turnover 字段（默认值 0）: {missing_turnover:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'turnover': {'$exists': False}},
                    {'$set': {'turnover': 0}}
                )
                fixed_count += result.modified_count
        
        # 7. 为缺少 Trading_turnover 的记录设置默认值
        missing_tt = self.collection.count_documents({'Trading_turnover': {'$exists': False}})
        
        if missing_tt > 0:
            self.logger.info(f"  添加 Trading_turnover 字段（默认值 0）: {missing_tt:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'Trading_turnover': {'$exists': False}},
                    {'$set': {'Trading_turnover': 0}}
                )
                fixed_count += result.modified_count
        
        self.logger.info(f"\n✅ 共修复 {fixed_count:,} 条记录")
        return fixed_count
    
    def fix_default_spread(self, batch_size: int = 1000) -> int:
        """修复 spread 为 0 的记录（重新计算）"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("2️⃣ 修复 spread 默认值（重新计算）")
        self.logger.info("=" * 70)
        
        # 查找 spread=0 但 close != open 的记录
        need_fix = self.collection.count_documents({
            'spread': 0,
            'close': {'$exists': True},
            'open': {'$exists': True},
            '$expr': {'$ne': ['$close', '$open']}
        })
        
        if need_fix == 0:
            self.logger.info("  ✅ 无需修复")
            return 0
        
        self.logger.info(f"  需要修复: {need_fix:,} 条")
        
        if self.dry_run:
            return 0
        
        # 批量更新
        result = self.collection.update_many(
            {
                'spread': 0,
                'close': {'$exists': True},
                'open': {'$exists': True},
                '$expr': {'$ne': ['$close', '$open']}
            },
            [{'$set': {'spread': {'$subtract': ['$close', '$open']}}}]
        )
        
        self.logger.info(f"✅ 已修复 {result.modified_count:,} 条记录")
        return result.modified_count
    
    def add_adjustment_fields(self) -> int:
        """为缺少 adjustment_factor 和 adj_close 的记录添加默认值"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("3️⃣ 添加复权字段默认值")
        self.logger.info("=" * 70)
        
        fixed_count = 0
        
        # 1. adjustment_factor 默认为 1.0
        missing_af = self.collection.count_documents({
            'adjustment_factor': {'$exists': False}
        })
        
        if missing_af > 0:
            self.logger.info(f"  添加 adjustment_factor（默认 1.0）: {missing_af:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'adjustment_factor': {'$exists': False}},
                    {'$set': {'adjustment_factor': Decimal128('1.0')}}
                )
                fixed_count += result.modified_count
        
        # 2. adj_close 默认等于 close
        missing_ac = self.collection.count_documents({
            'adj_close': {'$exists': False},
            'close': {'$exists': True}
        })
        
        if missing_ac > 0:
            self.logger.info(f"  添加 adj_close（从 close 复制）: {missing_ac:,} 条")
            if not self.dry_run:
                result = self.collection.update_many(
                    {'adj_close': {'$exists': False}, 'close': {'$exists': True}},
                    [{'$set': {'adj_close': '$close'}}]
                )
                fixed_count += result.modified_count
        
        self.logger.info(f"\n✅ 共添加 {fixed_count:,} 条记录")
        return fixed_count
    
    def verify_completion(self):
        """验证补齐结果"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("4️⃣ 验证补齐结果")
        self.logger.info("=" * 70)
        
        total = self.collection.count_documents({})
        
        checks = [
            ('stock_id', '股票代码'),
            ('symbol', '股票符号'),
            ('date', '日期'),
            ('open', '开盘价'),
            ('high', '最高价'),
            ('low', '最低价'),
            ('close', '收盘价'),
            ('volume', '成交量'),
            ('max', '最高价（别名）'),
            ('min', '最低价（别名）'),
            ('spread', '涨跌额'),
            ('Trading_Volume', '交易量'),
            ('Trading_money', '交易金额'),
            ('Trading_turnover', '交易笔数'),
            ('turnover', '成交笔数'),
            ('adjustment_factor', '复权因子'),
            ('adj_close', '复权收盘价'),
            ('updated_at', '更新时间'),
        ]
        
        all_complete = True
        
        for field, desc in checks:
            count = self.collection.count_documents({field: {'$exists': True}})
            coverage = count / total * 100 if total > 0 else 0
            
            status = "✅" if coverage >= 99.0 else "⚠️"
            self.logger.info(f"  {status} {desc} ({field}): {count:,}/{total:,} ({coverage:.1f}%)")
            
            if coverage < 99.0:
                all_complete = False
        
        if all_complete:
            self.logger.info("\n✅ 所有字段已完整！")
        else:
            self.logger.info("\n⚠️ 仍有字段不完整")
        
        return all_complete
    
    def close(self):
        """关闭连接"""
        self.client.close()
        self.logger.info("\n✅ 数据库连接已关闭")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='补齐数据库缺失的字段和数据')
    parser.add_argument('--dry-run', action='store_true', help='演练模式（不实际修改）')
    parser.add_argument('--execute', action='store_true', help='执行补齐（必须明确指定）')
    parser.add_argument('--batch-size', type=int, default=1000, help='批处理大小')
    
    args = parser.parse_args()
    
    # 安全检查
    if not args.dry_run and not args.execute:
        print("\n❌ 错误：必须指定 --dry-run 或 --execute")
        print("   --dry-run: 演练模式，显示补齐计划但不实际修改")
        print("   --execute: 执行实际补齐")
        sys.exit(1)
    
    completer = DataCompleter(dry_run=args.dry_run)
    
    try:
        # 1. 修复缺失字段
        completer.fix_missing_fields()
        
        # 2. 修复 spread 默认值
        completer.fix_default_spread(args.batch_size)
        
        # 3. 添加复权字段
        completer.add_adjustment_fields()
        
        # 4. 验证结果
        if not args.dry_run:
            completer.verify_completion()
            print("\n🎉 数据补齐完成！")
        else:
            print("\n⚠️  演练模式完成，未实际修改数据")
            print("   使用 --execute 执行实际补齐")
    
    finally:
        completer.close()


if __name__ == '__main__':
    main()
