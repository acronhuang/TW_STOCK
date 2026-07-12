#!/usr/bin/env python3
"""
数据迁移脚本：将 TWSE OpenAPI 格式的历史数据迁移到 FinMind 格式

迁移内容：
1. 添加 stock_id 字段（从 symbol 复制）
2. 更新 source 字段为 'finmind'
3. 重命名 updateTime 为 updated_at
4. 添加 FinMind 特有的字段（如有必要）
5. 删除旧数据

Author: GitHub Copilot
Date: 2026-02-24
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
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


class DataMigrator:
    """数据迁移工具"""
    
    def __init__(self, db_name: str = 'tw_stock_analysis', dry_run: bool = False):
        """
        初始化迁移器
        
        Args:
            db_name: 数据库名称
            dry_run: 是否为演练模式（不实际修改数据）
        """
        self.logger = setup_logger('DataMigrator')
        self.db_name = db_name
        self.dry_run = dry_run
        
        # 连接数据库
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        self.collection = self.db.stock_price
        
        self.logger.info(f"🔌 已连接到数据库: {db_name}")
        if dry_run:
            self.logger.warning("⚠️  演练模式：不会实际修改数据")
    
    def analyze_data(self) -> Dict[str, Any]:
        """分析当前数据状态"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("📊 数据分析")
        self.logger.info("=" * 70)
        
        # 统计数据
        total_count = self.collection.count_documents({})
        old_count = self.collection.count_documents({'stock_id': None})
        new_count = self.collection.count_documents({'stock_id': {'$ne': None}})
        
        self.logger.info(f"总记录数: {total_count:,}")
        self.logger.info(f"  ├─ 旧格式 (stock_id: null): {old_count:,} ({old_count/total_count*100:.2f}%)")
        self.logger.info(f"  └─ 新格式 (有 stock_id): {new_count:,} ({new_count/total_count*100:.2f}%)")
        
        # 统计旧数据涵盖的股票
        old_symbols = self.collection.distinct('symbol', {'stock_id': None})
        self.logger.info(f"\n旧数据涵盖股票数: {len(old_symbols)}")
        self.logger.info(f"示例股票: {', '.join(old_symbols[:10])}")
        
        # 检查字段差异
        old_sample = self.collection.find_one({'stock_id': None})
        new_sample = self.collection.find_one({'stock_id': {'$ne': None}})
        
        if old_sample and new_sample:
            old_fields = set(old_sample.keys()) - {'_id'}
            new_fields = set(new_sample.keys()) - {'_id'}
            
            self.logger.info(f"\n字段差异:")
            self.logger.info(f"  旧格式独有: {old_fields - new_fields}")
            self.logger.info(f"  新格式独有: {new_fields - old_fields}")
        
        return {
            'total_count': total_count,
            'old_count': old_count,
            'new_count': new_count,
            'old_symbols': old_symbols
        }
    
    def migrate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        迁移单条记录
        
        Args:
            record: 原始记录
            
        Returns:
            迁移后的记录
        """
        # 复制原记录
        migrated = record.copy()
        
        # 1. 添加 stock_id（从 symbol 复制）
        if 'symbol' in migrated and migrated.get('stock_id') is None:
            migrated['stock_id'] = migrated['symbol']
        
        # 2. 更新 source 字段
        if 'source' in migrated:
            del migrated['source']  # 删除旧的 source 字段
        
        # 3. 重命名 updateTime 为 updated_at
        if 'updateTime' in migrated:
            migrated['updated_at'] = migrated['updateTime']
            del migrated['updateTime']
        
        # 4. 确保有 updated_at 字段
        if 'updated_at' not in migrated:
            migrated['updated_at'] = datetime.now()
        
        # 5. 添加 FinMind 特有字段（如果不存在）
        # Trading_Volume, Trading_money, Trading_turnover 可以从 volume 计算或设为默认值
        if 'Trading_Volume' not in migrated and 'volume' in migrated:
            migrated['Trading_Volume'] = migrated['volume']
        
        if 'Trading_money' not in migrated:
            # 如果有 volume 和 cl close，可以估算
            if 'volume' in migrated and 'close' in migrated:
                volume = float(migrated['volume'].to_decimal()) if isinstance(migrated['volume'], Decimal128) else float(migrated['volume'])
                close_price = float(migrated['close'].to_decimal()) if isinstance(migrated['close'], Decimal128) else float(migrated['close'])
                migrated['Trading_money'] = int(volume * close_price)
        
        if 'Trading_turnover' not in migrated:
            migrated['Trading_turnover'] = 0  # 默认值
        
        if 'turnover' not in migrated:
            migrated['turnover'] = 0  # 默认值
        
        # 6. 添加 max, min, spread（如果不存在）
        if 'max' not in migrated and 'high' in migrated:
            migrated['max'] = migrated['high']
        
        if 'min' not in migrated and 'low' in migrated:
            migrated['min'] = migrated['low']
        
        if 'spread' not in migrated:
            if 'close' in migrated and 'open' in migrated:
                close_val = float(migrated['close'].to_decimal()) if isinstance(migrated['close'], Decimal128) else float(migrated['close'])
                open_val = float(migrated['open'].to_decimal()) if isinstance(migrated['open'], Decimal128) else float(migrated['open'])
                migrated['spread'] = round(close_val - open_val, 2)
            else:
                migrated['spread'] = 0
        
        return migrated
    
    def migrate_batch(self, batch_size: int = 1000) -> int:
        """
        批量迁移数据
        
        Args:
            batch_size: 每批处理的记录数
            
        Returns:
            迁移的记录数
        """
        self.logger.info("\n" + "=" * 70)
        self.logger.info("🔄 开始批量迁移")
        self.logger.info("=" * 70)
        
        # 获取所有需要迁移的记录ID
        old_records = self.collection.find(
            {'stock_id': None},
            {'_id': 1}
        )
        old_ids = [r['_id'] for r in old_records]
        total_to_migrate = len(old_ids)
        
        self.logger.info(f"待迁移记录数: {total_to_migrate:,}")
        
        if total_to_migrate == 0:
            self.logger.info("✅ 没有需要迁移的记录")
            return 0
        
        if self.dry_run:
            self.logger.warning("⚠️  演练模式：显示前 5 条迁移示例")
            sample_records = self.collection.find({'stock_id': None}).limit(5)
            for i, record in enumerate(sample_records, 1):
                self.logger.info(f"\n示例 {i}:")
                self.logger.info(f"  原始: symbol={record.get('symbol')}, stock_id={record.get('stock_id')}")
                migrated = self.migrate_record(record)
                self.logger.info(f"  迁移后: symbol={migrated.get('symbol')}, stock_id={migrated.get('stock_id')}")
            return 0
        
        # 批量处理
        migrated_count = 0
        for i in range(0, total_to_migrate, batch_size):
            batch_ids = old_ids[i:i + batch_size]
            batch_records = self.collection.find({'_id': {'$in': batch_ids}})
            
            bulk_operations = []
            for record in batch_records:
                migrated = self.migrate_record(record)
                bulk_operations.append(
                    pymongo.UpdateOne(
                        {'_id': record['_id']},
                        {'$set': migrated}
                    )
                )
            
            if bulk_operations:
                result = self.collection.bulk_write(bulk_operations)
                migrated_count += result.modified_count
                
                progress = (i + len(batch_ids)) / total_to_migrate * 100
                self.logger.info(f"进度: {progress:.1f}% ({migrated_count:,}/{total_to_migrate:,})")
        
        self.logger.info(f"\n✅ 迁移完成: {migrated_count:,} 条记录")
        return migrated_count
    
    def verify_migration(self) -> bool:
        """验证迁移结果"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("🔍 验证迁移结果")
        self.logger.info("=" * 70)
        
        # 检查是否还有 stock_id 为 null 的记录
        remaining_old = self.collection.count_documents({'stock_id': None})
        
        if remaining_old > 0:
            self.logger.error(f"❌ 发现 {remaining_old:,} 条未迁移的记录")
            return False
        
        # 检查所有记录是否有必需字段
        total_count = self.collection.count_documents({})
        records_with_stock_id = self.collection.count_documents({'stock_id': {'$ne': None}})
        records_with_updated_at = self.collection.count_documents({'updated_at': {'$exists': True}})
        
        self.logger.info(f"总记录数: {total_count:,}")
        self.logger.info(f"有 stock_id 的记录: {records_with_stock_id:,}")
        self.logger.info(f"有 updated_at 的记录: {records_with_updated_at:,}")
        
        if records_with_stock_id == total_count and records_with_updated_at == total_count:
            self.logger.info("✅ 所有记录都已正确迁移")
            return True
        else:
            self.logger.error("❌ 部分记录缺少必需字段")
            return False
    
    def cleanup_old_source_field(self) -> int:
        """清理旧的 source 字段"""
        if self.dry_run:
            count = self.collection.count_documents({'source': {'$exists': True}})
            self.logger.warning(f"⚠️  演练模式：将删除 {count:,} 条记录的 source 字段")
            return 0
        
        self.logger.info("\n" + "=" * 70)
        self.logger.info("🧹 清理旧字段")
        self.logger.info("=" * 70)
        
        # 删除所有记录的 source 字段
        result = self.collection.update_many(
            {'source': {'$exists': True}},
            {'$unset': {'source': ''}}
        )
        
        self.logger.info(f"✅ 已清理 {result.modified_count:,} 条记录的 source 字段")
        return result.modified_count
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()
        self.logger.info("\n✅ 数据库连接已关闭")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='数据迁移工具：TWSE OpenAPI → FinMind 格式')
    parser.add_argument('--dry-run', action='store_true', help='演练模式（不实际修改数据）')
    parser.add_argument('--execute', action='store_true', help='执行迁移（必须明确指定）')
    parser.add_argument('--batch-size', type=int, default=1000, help='每批处理的记录数')
    
    args = parser.parse_args()
    
    # 安全检查
    if not args.dry_run and not args.execute:
        print("\n❌ 错误：必须指定 --dry-run 或 --execute")
        print("   --dry-run: 演练模式，显示迁移计划但不实际修改")
        print("   --execute: 执行实际迁移")
        sys.exit(1)
    
    # 创建迁移器
    migrator = DataMigrator(dry_run=args.dry_run)
    
    try:
        # 1. 分析数据
        stats = migrator.analyze_data()
        
        # 2. 执行迁移
        if stats['old_count'] > 0:
            if not args.dry_run:
                # 确认执行
                print(f"\n⚠️  即将迁移 {stats['old_count']:,} 条记录")
                print(f"   涉及 {len(stats['old_symbols'])} 支股票")
                print(f"   是否继续？(yes/no): ", end='')
                
                response = input().strip().lower()
                if response != 'yes':
                    print("❌ 已取消迁移")
                    return
            
            migrated_count = migrator.migrate_batch(batch_size=args.batch_size)
            
            if not args.dry_run and migrated_count > 0:
                # 3. 验证迁移
                if migrator.verify_migration():
                    # 4. 清理旧字段
                    migrator.cleanup_old_source_field()
                    print("\n🎉 迁移完成！")
                else:
                    print("\n❌ 迁移验证失败")
                    sys.exit(1)
        else:
            print("\n✅ 所有数据已是新格式，无需迁移")
    
    finally:
        migrator.close()


if __name__ == '__main__':
    main()
