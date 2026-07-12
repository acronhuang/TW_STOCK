#!/usr/bin/env python3
"""
清理字段命名冗余

问题:
- tickers 集合同时存在 close 和 closePrice 字段
- tickers 集合同时存在 volume 和 tradeVolume 字段
- stock_price 集合同时存在 close 和 closePrice 字段
- stock_price 集合同时存在 volume 和 tradeVolume 字段

解决方案:
- 保留 closePrice (符合 camelCase 规范)，删除 close
- 保留 tradeVolume (符合 camelCase 规范)，删除 volume

作者: Professional Financial Systems Architect
日期: 2026-02-21
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Any
import logging

from pymongo import MongoClient, UpdateMany

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class FieldCleanup:
    """字段冗余清理器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
    
    def check_field_status(self, collection_name: str, field_pairs: List[tuple]) -> Dict[str, Any]:
        """检查字段状态"""
        collection = self.db[collection_name]
        total = collection.count_documents({})
        
        status = {
            'collection': collection_name,
            'total': total,
            'fields': {}
        }
        
        for old_field, new_field in field_pairs:
            has_old = collection.count_documents({old_field: {'$exists': True}})
            has_new = collection.count_documents({new_field: {'$exists': True}})
            has_both = collection.count_documents({
                old_field: {'$exists': True},
                new_field: {'$exists': True}
            })
            
            status['fields'][f'{old_field}->{new_field}'] = {
                'old_field': old_field,
                'new_field': new_field,
                'has_old': has_old,
                'has_new': has_new,
                'has_both': has_both
            }
        
        return status
    
    def cleanup_collection(self, collection_name: str, fields_to_remove: List[str]) -> Dict[str, Any]:
        """清理集合中的冗余字段"""
        collection = self.db[collection_name]
        
        logger.info(f'\n处理集合: {collection_name}')
        logger.info('=' * 60)
        
        result = {
            'collection': collection_name,
            'fields_removed': [],
            'modified_count': 0
        }
        
        for field in fields_to_remove:
            # 检查字段存在数量
            count_before = collection.count_documents({field: {'$exists': True}})
            
            if count_before == 0:
                logger.info(f'✅ 字段 "{field}" 不存在，无需删除')
                continue
            
            logger.info(f'🔍 发现 {count_before:,} 笔记录包含字段 "{field}"')
            
            # 备份样本（用于验证）
            sample_before = collection.find_one({field: {'$exists': True}})
            
            # 删除字段
            logger.info(f'🗑️  正在删除字段 "{field}"...')
            update_result = collection.update_many(
                {field: {'$exists': True}},
                {'$unset': {field: ''}}
            )
            
            # 验证删除
            count_after = collection.count_documents({field: {'$exists': True}})
            
            if count_after == 0:
                logger.info(f'✅ 成功删除字段 "{field}" ({update_result.modified_count:,} 笔记录)')
                result['fields_removed'].append(field)
                result['modified_count'] += update_result.modified_count
            else:
                logger.error(f'❌ 删除失败，仍有 {count_after:,} 笔记录包含字段 "{field}"')
        
        return result
    
    def verify_cleanup(self, collection_name: str, field_pairs: List[tuple]):
        """验证清理结果"""
        logger.info(f'\n验证集合: {collection_name}')
        logger.info('=' * 60)
        
        collection = self.db[collection_name]
        
        for old_field, new_field in field_pairs:
            has_old = collection.count_documents({old_field: {'$exists': True}})
            has_new = collection.count_documents({new_field: {'$exists': True}})
            
            logger.info(f'{old_field} -> {new_field}:')
            logger.info(f'  旧字段 ({old_field}): {has_old:,} 笔 {"❌ 应为 0" if has_old > 0 else "✅"}')
            logger.info(f'  新字段 ({new_field}): {has_new:,} 笔 {"✅" if has_new > 0 else "⚠️ 无数据"}')
        
        # 显示样本
        sample = collection.find_one({})
        if sample:
            logger.info('\n样本记录字段:')
            fields = list(sample.keys())
            logger.info(f'  {", ".join(fields)}')
    
    def run_cleanup(self):
        """执行完整清理流程"""
        logger.info('开始清理字段冗余...')
        logger.info('=' * 60)
        
        # 定义要清理的集合和字段
        cleanup_tasks = [
            {
                'collection': 'tickers',
                'field_pairs': [
                    ('close', 'closePrice'),
                    ('volume', 'tradeVolume')
                ],
                'fields_to_remove': ['close', 'volume']
            },
            {
                'collection': 'stock_price',
                'field_pairs': [
                    ('close', 'closePrice'),
                    ('volume', 'tradeVolume')
                ],
                'fields_to_remove': ['close', 'volume']
            }
        ]
        
        results = []
        
        for task in cleanup_tasks:
            collection = task['collection']
            field_pairs = task['field_pairs']
            fields_to_remove = task['fields_to_remove']
            
            # 检查状态
            status = self.check_field_status(collection, field_pairs)
            logger.info(f'\n【清理前状态】集合: {collection}')
            logger.info(f'总记录数: {status["total"]:,}')
            for field_info in status['fields'].values():
                old = field_info['old_field']
                new = field_info['new_field']
                logger.info(f'{old}: {field_info["has_old"]:,} 笔')
                logger.info(f'{new}: {field_info["has_new"]:,} 笔')
                logger.info(f'两者都有: {field_info["has_both"]:,} 笔')
            
            # 执行清理
            result = self.cleanup_collection(collection, fields_to_remove)
            results.append(result)
            
            # 验证清理
            self.verify_cleanup(collection, field_pairs)
        
        # 打印摘要
        logger.info('\n' + '=' * 60)
        logger.info('清理摘要')
        logger.info('=' * 60)
        
        for result in results:
            logger.info(f'\n集合: {result["collection"]}')
            logger.info(f'删除字段: {", ".join(result["fields_removed"])}')
            logger.info(f'修改记录数: {result["modified_count"]:,}')
        
        logger.info('\n✅ 字段冗余清理完成!')
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    try:
        cleanup = FieldCleanup()
        cleanup.run_cleanup()
        cleanup.close()
        return 0
    
    except Exception as e:
        logger.error(f'执行失败: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
