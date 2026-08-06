#!/usr/bin/env python3
"""
修复数据验证发现的关键问题

高优先级 (P0):
1. stock_price 缺少 closePrice/tradeVolume 字段 → 从 close/volume 复制
2. 价格逻辑错误 (high < close 或 low > close) → 标记为无效

中优先级 (P1):
3. 股价为 0 的股票 → 标记为停牌
4. 极端 ROE 数据 → 标记为异常

作者: Professional Financial Systems Architect
日期: 2026-02-21
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
import logging

from pymongo import MongoClient, UpdateOne, UpdateMany
from bson.decimal128 import Decimal128

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class CriticalIssuesFixer:
    """关键问题修复器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.stats = {
            'field_migration': {'success': 0, 'failed': 0},
            'price_logic_errors': {'found': 0, 'fixed': 0},
            'zero_price_stocks': {'found': 0, 'marked': 0},
            'extreme_roe': {'found': 0, 'marked': 0}
        }
    
    def check_field_status(self):
        """检查字段状态"""
        logger.info('检查 stock_price 字段状态...')
        logger.info('=' * 60)
        
        total = self.db.stock_price.count_documents({})
        has_close = self.db.stock_price.count_documents({'close': {'$exists': True}})
        has_closePrice = self.db.stock_price.count_documents({'closePrice': {'$exists': True}})
        has_volume = self.db.stock_price.count_documents({'volume': {'$exists': True}})
        has_tradeVolume = self.db.stock_price.count_documents({'tradeVolume': {'$exists': True}})
        
        logger.info(f'总记录: {total:,}')
        logger.info(f'有 close: {has_close:,} ({has_close/total*100:.1f}%)')
        logger.info(f'有 closePrice: {has_closePrice:,} ({has_closePrice/total*100:.1f}%)')
        logger.info(f'有 volume: {has_volume:,} ({has_volume/total*100:.1f}%)')
        logger.info(f'有 tradeVolume: {has_tradeVolume:,} ({has_tradeVolume/total*100:.1f}%)')
        
        return {
            'total': total,
            'has_close': has_close,
            'has_closePrice': has_closePrice,
            'has_volume': has_volume,
            'has_tradeVolume': has_tradeVolume
        }
    
    def fix_missing_fields(self):
        """修复缺失的标准字段"""
        logger.info('\n【任务 1】修复 stock_price 缺失字段')
        logger.info('=' * 60)
        
        # 复制 close → closePrice
        missing_closePrice = self.db.stock_price.count_documents({
            'close': {'$exists': True},
            'closePrice': {'$exists': False}
        })
        
        if missing_closePrice > 0:
            logger.info(f'发现 {missing_closePrice:,} 笔记录缺少 closePrice')
            logger.info('正在从 close 字段复制...')
            
            # 使用 aggregation pipeline 更新
            # MongoDB 4.2+ 支持 aggregation pipeline in update
            result = self.db.stock_price.update_many(
                {
                    'close': {'$exists': True},
                    'closePrice': {'$exists': False}
                },
                [
                    {'$set': {'closePrice': '$close'}}
                ]
            )
            
            logger.info(f'✅ 成功复制 closePrice: {result.modified_count:,} 笔')
            self.stats['field_migration']['success'] += result.modified_count
        else:
            logger.info('✅ 所有记录都有 closePrice 字段')
        
        # 复制 volume → tradeVolume
        missing_tradeVolume = self.db.stock_price.count_documents({
            'volume': {'$exists': True},
            'tradeVolume': {'$exists': False}
        })
        
        if missing_tradeVolume > 0:
            logger.info(f'\n发现 {missing_tradeVolume:,} 笔记录缺少 tradeVolume')
            logger.info('正在从 volume 字段复制...')
            
            result = self.db.stock_price.update_many(
                {
                    'volume': {'$exists': True},
                    'tradeVolume': {'$exists': False}
                },
                [
                    {'$set': {'tradeVolume': '$volume'}}
                ]
            )
            
            logger.info(f'✅ 成功复制 tradeVolume: {result.modified_count:,} 笔')
            self.stats['field_migration']['success'] += result.modified_count
        else:
            logger.info('✅ 所有记录都有 tradeVolume 字段')
    
    def fix_price_logic_errors(self):
        """修复价格逻辑错误"""
        logger.info('\n【任务 2】修复价格逻辑错误')
        logger.info('=' * 60)
        
        # 查找价格逻辑错误: high < close 或 low > close
        pipeline = [
            {
                '$match': {
                    'high': {'$exists': True},
                    'low': {'$exists': True},
                    'close': {'$exists': True}
                }
            },
            {
                '$addFields': {
                    'highNum': {'$toDouble': '$high'},
                    'lowNum': {'$toDouble': '$low'},
                    'closeNum': {'$toDouble': '$close'}
                }
            },
            {
                '$match': {
                    '$or': [
                        {'$expr': {'$lt': ['$highNum', '$closeNum']}},
                        {'$expr': {'$gt': ['$lowNum', '$closeNum']}}
                    ]
                }
            },
            {
                '$project': {
                    'symbol': 1,
                    'date': 1,
                    'high': 1,
                    'low': 1,
                    'close': 1
                }
            }
        ]
        
        errors = list(self.db.stock_price.aggregate(pipeline))
        self.stats['price_logic_errors']['found'] = len(errors)
        
        if errors:
            logger.info(f'发现 {len(errors)} 笔价格逻辑错误:')
            
            bulk_operations = []
            
            for error in errors:
                symbol = error.get('symbol', 'UNKNOWN')
                date = error.get('date', 'UNKNOWN')
                high = error.get('high')
                low = error.get('low')
                close = error.get('close')
                
                logger.warning(f'  {symbol} ({date}): high={high}, close={close}, low={low}')
                
                # 标记为无效数据
                bulk_operations.append(
                    UpdateOne(
                        {'_id': error['_id']},
                        {
                            '$set': {
                                'dataQuality': 'INVALID',
                                'dataQualityReason': 'Price logic error: high/low/close inconsistent',
                                'dataQualityCheckedAt': datetime.now()
                            }
                        }
                    )
                )
            
            if bulk_operations:
                result = self.db.stock_price.bulk_write(bulk_operations)
                logger.info(f'✅ 已标记 {result.modified_count} 笔为无效数据')
                self.stats['price_logic_errors']['fixed'] = result.modified_count
        else:
            logger.info('✅ 未发现价格逻辑错误')
    
    def fix_zero_price_stocks(self):
        """处理股价为 0 的股票"""
        logger.info('\n【任务 3】处理股价为 0 的股票')
        logger.info('=' * 60)
        
        # 查找股价为 0 的股票
        zero_price_stocks = list(self.db.tickers.find(
            {
                '$or': [
                    {'closePrice': Decimal128(Decimal('0'))},
                    {'closePrice': 0},
                    {'closePrice': {'$lte': 0}}
                ]
            },
            {'symbol': 1, 'name': 1, 'closePrice': 1}
        ))
        
        self.stats['zero_price_stocks']['found'] = len(zero_price_stocks)
        
        if zero_price_stocks:
            logger.info(f'发现 {len(zero_price_stocks)} 档股价为 0 的股票:')
            
            for stock in zero_price_stocks:
                symbol = stock.get('symbol', 'UNKNOWN')
                name = stock.get('name', 'N/A')
                logger.warning(f'  {symbol} ({name}): 股价={stock.get("closePrice")}')
            
            # 标记为停牌
            result = self.db.tickers.update_many(
                {
                    '$or': [
                        {'closePrice': Decimal128(Decimal('0'))},
                        {'closePrice': 0},
                        {'closePrice': {'$lte': 0}}
                    ]
                },
                {
                    '$set': {
                        'tradingStatus': 'SUSPENDED',
                        'tradingStatusReason': 'Zero price detected',
                        'tradingStatusCheckedAt': datetime.now()
                    }
                }
            )
            
            logger.info(f'✅ 已标记 {result.modified_count} 档为停牌状态')
            self.stats['zero_price_stocks']['marked'] = result.modified_count
        else:
            logger.info('✅ 未发现股价为 0 的股票')
    
    def fix_extreme_roe(self):
        """标记极端 ROE 数据"""
        logger.info('\n【任务 4】标记极端 ROE 数据')
        logger.info('=' * 60)
        
        # 查找极端 ROE (< -100% 或 > 100%)
        extreme_roe = list(self.db.financial_reports.find(
            {
                '$or': [
                    {'ratios.roe': {'$lt': -100}},
                    {'ratios.roe': {'$gt': 100}}
                ]
            },
            {'symbol': 1, 'fiscalYear': 1, 'fiscalPeriod': 1, 'ratios.roe': 1}
        ).limit(50))
        
        # 同时查找总数
        extreme_count = self.db.financial_reports.count_documents({
            '$or': [
                {'ratios.roe': {'$lt': -100}},
                {'ratios.roe': {'$gt': 100}}
            ]
        })
        
        self.stats['extreme_roe']['found'] = extreme_count
        
        if extreme_roe:
            logger.info(f'发现 {extreme_count} 笔极端 ROE 数据 (显示前 {len(extreme_roe)} 笔):')
            
            for report in extreme_roe[:10]:
                symbol = report.get('symbol', 'UNKNOWN')
                year = report.get('fiscalYear', 'N/A')
                period = report.get('fiscalPeriod', 'N/A')
                roe = report.get('ratios', {}).get('roe', 'N/A')
                logger.warning(f'  {symbol} {year}{period}: ROE={roe:.2f}%')
            
            if len(extreme_roe) > 10:
                logger.info(f'  ... 还有 {len(extreme_roe) - 10} 笔')
            
            # 标记为异常数据
            result = self.db.financial_reports.update_many(
                {
                    '$or': [
                        {'ratios.roe': {'$lt': -100}},
                        {'ratios.roe': {'$gt': 100}}
                    ]
                },
                {
                    '$set': {
                        'dataQuality': 'EXTREME_VALUE',
                        'dataQualityReason': 'ROE outside normal range [-100%, 100%]',
                        'dataQualityCheckedAt': datetime.now()
                    }
                }
            )
            
            logger.info(f'✅ 已标记 {result.modified_count} 笔为极端数据')
            self.stats['extreme_roe']['marked'] = result.modified_count
        else:
            logger.info('✅ 未发现极端 ROE 数据')
    
    def print_summary(self):
        """打印执行摘要"""
        logger.info('\n' + '=' * 60)
        logger.info('执行摘要')
        logger.info('=' * 60)
        
        logger.info('\n字段迁移:')
        logger.info(f'  成功: {self.stats["field_migration"]["success"]:,} 笔')
        logger.info(f'  失败: {self.stats["field_migration"]["failed"]:,} 笔')
        
        logger.info('\n价格逻辑错误:')
        logger.info(f'  发现: {self.stats["price_logic_errors"]["found"]:,} 笔')
        logger.info(f'  已修复: {self.stats["price_logic_errors"]["fixed"]:,} 笔')
        
        logger.info('\n股价为 0:')
        logger.info(f'  发现: {self.stats["zero_price_stocks"]["found"]:,} 档')
        logger.info(f'  已标记: {self.stats["zero_price_stocks"]["marked"]:,} 档')
        
        logger.info('\n极端 ROE:')
        logger.info(f'  发现: {self.stats["extreme_roe"]["found"]:,} 笔')
        logger.info(f'  已标记: {self.stats["extreme_roe"]["marked"]:,} 笔')
        
        logger.info('\n' + '=' * 60)
    
    def run_all_fixes(self):
        """执行所有修复"""
        logger.info('开始修复关键问题...')
        logger.info('=' * 60)
        
        # 检查状态
        self.check_field_status()
        
        # 执行修复
        self.fix_missing_fields()
        self.fix_price_logic_errors()
        self.fix_zero_price_stocks()
        self.fix_extreme_roe()
        
        # 打印摘要
        self.print_summary()
        
        # 再次检查状态
        logger.info('\n最终状态:')
        self.check_field_status()
        
        logger.info('\n✅ 所有关键问题修复完成!')
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    try:
        fixer = CriticalIssuesFixer()
        fixer.run_all_fixes()
        fixer.close()
        return 0
    
    except Exception as e:
        logger.error(f'执行失败: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
