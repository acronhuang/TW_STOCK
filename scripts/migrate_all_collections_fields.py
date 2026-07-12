#!/usr/bin/env python3
"""
集合字段标准化迁移脚本
=====================
将所有集合统一迁移到 FinMind 标准字段名

迁移内容：
1. financial_reports: updateTime → updated_at
2. financial_statements: updateTime → updated_at, 删除 source
3. taiwan_stock_per: 添加 updated_at

Author: GitHub Copilot
Date: 2026-02-24
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import pymongo
from pymongo import MongoClient

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class CollectionFieldMigrator:
    """集合字段迁移工具"""
    
    def __init__(self, db_name: str = 'tw_stock_analysis'):
        """初始化迁移工具"""
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        print(f"📁 连接到数据库: {db_name}")
    
    def backup_collection(self, collection_name: str) -> str:
        """备份集合"""
        backup_name = f"{collection_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"\n📦 备份集合: {collection_name} → {backup_name}")
        
        # 使用 MongoDB 的复制功能
        source = self.db[collection_name]
        target = self.db[backup_name]
        
        # 复制所有文档
        count = 0
        batch_size = 1000
        
        for doc in source.find().batch_size(batch_size):
            target.insert_one(doc)
            count += 1
            if count % 10000 == 0:
                print(f"  已备份: {count:,} 条")
        
        print(f"✅ 备份完成: {count:,} 条记录")
        return backup_name
    
    def migrate_financial_reports(self) -> Dict[str, Any]:
        """迁移 financial_reports 集合"""
        collection = self.db.financial_reports
        
        print("\n" + "="*60)
        print("📊 迁移 financial_reports 集合")
        print("="*60)
        
        # 1. 统计当前状态
        total = collection.count_documents({})
        with_update_time = collection.count_documents({'updateTime': {'$exists': True}})
        with_updated_at = collection.count_documents({'updated_at': {'$exists': True}})
        
        print(f"\n当前状态:")
        print(f"  总记录数: {total:,}")
        print(f"  有 updateTime: {with_update_time:,}")
        print(f"  有 updated_at: {with_updated_at:,}")
        
        if with_update_time == 0:
            print("✅ 无需迁移，字段已标准化")
            return {'status': 'skip', 'reason': '无需迁移'}
        
        # 2. 备份
        backup_name = self.backup_collection('financial_reports')
        
        # 3. 执行迁移
        print(f"\n🔄 执行迁移...")
        
        updated = 0
        batch = []
        batch_size = 1000
        
        for doc in collection.find({'updateTime': {'$exists': True}}):
            # 重命名 updateTime → updated_at
            operations = {
                '$set': {
                    'updated_at': doc['updateTime']
                },
                '$unset': {
                    'updateTime': ''
                }
            }
            
            batch.append(
                pymongo.UpdateOne(
                    {'_id': doc['_id']},
                    operations
                )
            )
            
            if len(batch) >= batch_size:
                result = collection.bulk_write(batch, ordered=False)
                updated += result.modified_count
                batch = []
                print(f"  已迁移: {updated:,} 条")
        
        # 处理剩余批次
        if batch:
            result = collection.bulk_write(batch, ordered=False)
            updated += result.modified_count
        
        print(f"✅ 迁移完成: {updated:,} 条记录")
        
        # 4. 验证
        after_check = collection.count_documents({'updateTime': {'$exists': True}})
        print(f"✓ 验证: 剩余 updateTime 字段: {after_check}")
        
        return {
            'status': 'success',
            'total': total,
            'updated': updated,
            'backup': backup_name
        }
    
    def migrate_financial_statements(self) -> Dict[str, Any]:
        """迁移 financial_statements 集合"""
        collection = self.db.financial_statements
        
        print("\n" + "="*60)
        print("📊 迁移 financial_statements 集合")
        print("="*60)
        
        # 1. 统计当前状态
        total = collection.count_documents({})
        with_update_time = collection.count_documents({'updateTime': {'$exists': True}})
        with_source = collection.count_documents({'source': {'$exists': True}})
        with_updated_at = collection.count_documents({'updated_at': {'$exists': True}})
        
        print(f"\n当前状态:")
        print(f"  总记录数: {total:,}")
        print(f"  有 updateTime: {with_update_time:,}")
        print(f"  有 source: {with_source:,}")
        print(f"  有 updated_at: {with_updated_at:,}")
        
        if with_update_time == 0 and with_source == 0:
            print("✅ 无需迁移，字段已标准化")
            return {'status': 'skip', 'reason': '无需迁移'}
        
        # 2. 备份
        backup_name = self.backup_collection('financial_statements')
        
        # 3. 执行迁移
        print(f"\n🔄 执行迁移...")
        
        updated = 0
        batch = []
        batch_size = 1000
        
        for doc in collection.find({}):
            operations = {}
            set_ops = {}
            unset_ops = {}
            
            # 重命名 updateTime → updated_at
            if 'updateTime' in doc:
                set_ops['updated_at'] = doc['updateTime']
                unset_ops['updateTime'] = ''
            
            # 删除 source 字段
            if 'source' in doc:
                unset_ops['source'] = ''
            
            # 确保有 updated_at
            if 'updated_at' not in doc and 'updateTime' not in doc:
                set_ops['updated_at'] = datetime.now()
            
            if set_ops:
                operations['$set'] = set_ops
            if unset_ops:
                operations['$unset'] = unset_ops
            
            if operations:
                batch.append(
                    pymongo.UpdateOne(
                        {'_id': doc['_id']},
                        operations
                    )
                )
            
            if len(batch) >= batch_size:
                result = collection.bulk_write(batch, ordered=False)
                updated += result.modified_count
                batch = []
                print(f"  已迁移: {updated:,} 条")
        
        # 处理剩余批次
        if batch:
            result = collection.bulk_write(batch, ordered=False)
            updated += result.modified_count
        
        print(f"✅ 迁移完成: {updated:,} 条记录")
        
        # 4. 验证
        after_update_time = collection.count_documents({'updateTime': {'$exists': True}})
        after_source = collection.count_documents({'source': {'$exists': True}})
        after_updated_at = collection.count_documents({'updated_at': {'$exists': True}})
        
        print(f"✓ 验证:")
        print(f"  剩余 updateTime: {after_update_time}")
        print(f"  剩余 source: {after_source}")
        print(f"  拥有 updated_at: {after_updated_at}")
        
        return {
            'status': 'success',
            'total': total,
            'updated': updated,
            'backup': backup_name
        }
    
    def migrate_taiwan_stock_per(self) -> Dict[str, Any]:
        """迁移 taiwan_stock_per 集合"""
        collection = self.db.taiwan_stock_per
        
        print("\n" + "="*60)
        print("📊 迁移 taiwan_stock_per 集合")
        print("="*60)
        
        # 1. 统计当前状态
        total = collection.count_documents({})
        with_updated_at = collection.count_documents({'updated_at': {'$exists': True}})
        
        print(f"\n当前状态:")
        print(f"  总记录数: {total:,}")
        print(f"  有 updated_at: {with_updated_at:,}")
        
        if with_updated_at == total:
            print("✅ 无需迁移，字段已标准化")
            return {'status': 'skip', 'reason': '无需迁移'}
        
        # 2. 备份
        backup_name = self.backup_collection('taiwan_stock_per')
        
        # 3. 执行迁移 - 添加 updated_at 字段
        print(f"\n🔄 执行迁移...")
        
        need_update = total - with_updated_at
        print(f"  需要添加 updated_at 的记录: {need_update:,}")
        
        # 批量添加 updated_at
        result = collection.update_many(
            {'updated_at': {'$exists': False}},
            {'$set': {'updated_at': datetime.now()}}
        )
        
        print(f"✅ 迁移完成: {result.modified_count:,} 条记录")
        
        # 4. 验证
        after_check = collection.count_documents({'updated_at': {'$exists': True}})
        print(f"✓ 验证: 拥有 updated_at: {after_check:,}/{total:,}")
        
        return {
            'status': 'success',
            'total': total,
            'updated': result.modified_count,
            'backup': backup_name
        }
    
    def run_migration(self):
        """执行所有迁移"""
        print("\n" + "="*60)
        print("🚀 集合字段标准化迁移")
        print("="*60)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        results = {}
        
        # 1. 迁移 financial_reports
        try:
            results['financial_reports'] = self.migrate_financial_reports()
        except Exception as e:
            print(f"❌ financial_reports 迁移失败: {e}")
            results['financial_reports'] = {'status': 'error', 'error': str(e)}
        
        # 2. 迁移 financial_statements  
        try:
            results['financial_statements'] = self.migrate_financial_statements()
        except Exception as e:
            print(f"❌ financial_statements 迁移失败: {e}")
            results['financial_statements'] = {'status': 'error', 'error': str(e)}
        
        # 3. 迁移 taiwan_stock_per
        try:
            results['taiwan_stock_per'] = self.migrate_taiwan_stock_per()
        except Exception as e:
            print(f"❌ taiwan_stock_per 迁移失败: {e}")
            results['taiwan_stock_per'] = {'status': 'error', 'error': str(e)}
        
        # 总结
        print("\n" + "="*60)
        print("📋 迁移总结")
        print("="*60)
        
        for collection, result in results.items():
            status_icon = "✅" if result['status'] == 'success' else "⏭️" if result['status'] == 'skip' else "❌"
            print(f"\n{status_icon} {collection}:")
            
            if result['status'] == 'success':
                print(f"    总记录: {result['total']:,}")
                print(f"    已更新: {result['updated']:,}")
                print(f"    备份: {result['backup']}")
            elif result['status'] == 'skip':
                print(f"    {result['reason']}")
            else:
                print(f"    错误: {result.get('error')}")
        
        print(f"\n完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        return results


def main():
    """主函数"""
    migrator = CollectionFieldMigrator()
    migrator.run_migration()


if __name__ == '__main__':
    main()
