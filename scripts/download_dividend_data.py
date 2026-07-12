#!/usr/bin/env python3
"""
补充历史股利数据脚本
根据审计报告发现的问题，补充 2015-2025 年的完整股利数据
目标：从 73 笔扩充至 13,000+ 笔

执行前状态：
- 股利记录: 73 笔
- 覆盖股票: 10 档
- 覆盖率: 0.74%

执行后目标：
- 股利记录: 13,000+ 笔
- 覆盖股票: 1,300+ 档
- 覆盖率: 95%+
"""

import os
import sys
import logging
from datetime import datetime
from pymongo import MongoClient

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.downloaders.finmind_client import FinMindClient
from src.downloaders.data_validator import DataValidator


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(__name__)


def get_all_stock_symbols(db) -> list:
    """从数据库获取所有股票代码"""
    # 尝试从 tickers 集合获取
    tickers = list(db.tickers.find({}, {'symbol': 1, '_id': 0}))
    if tickers:
        return [t['symbol'] for t in tickers]
    
    # 如果没有 tickers，从 stock_price 获取一般股票（排除 ETF/權證/0開頭）
    all_syms = db.stock_price.distinct('symbol')
    return sorted(s for s in all_syms if s.isdigit() and len(s) == 4 and not s.startswith('0'))


def download_dividend_data(
    api_token: str,
    mongo_uri: str = "mongodb://localhost:27017/",
    db_name: str = "tw_stock_analysis",
    start_date: str = "2015-01-01"
):
    """
    下载股利数据
    
    Args:
        api_token: FinMind API Token
        mongo_uri: MongoDB 连接 URI
        db_name: 数据库名称
        start_date: 开始日期 (建议 2015-01-01)
    """
    logger = setup_logging()
    
    logger.info('='*80)
    logger.info('补充历史股利数据')
    logger.info('='*80)
    
    # 连接数据库
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client[db_name]
    
    # 初始化 FinMind 客户端
    api_client = FinMindClient(api_token, logger)
    validator = DataValidator(logger)
    
    # 获取所有股票代码
    logger.info('\n📊 获取股票列表...')
    symbols = get_all_stock_symbols(db)
    logger.info(f'找到 {len(symbols)} 档股票')
    
    # 检查当前股利数据状态
    current_count = db.dividend_results.count_documents({})
    current_stocks = len(db.dividend_results.distinct('symbol'))
    logger.info(f'\n当前状态:')
    logger.info(f'  股利记录: {current_count:,} 笔')
    logger.info(f'  覆盖股票: {current_stocks} 档')
    logger.info(f'  覆盖率: {current_stocks/len(symbols)*100:.2f}%')
    
    # 下载股利政策表 (TaiwanStockDividend)
    logger.info(f'\n🔄 开始下载股利政策表 (TaiwanStockDividend)...')
    logger.info(f'时间范围: {start_date} ~ 现在')
    
    dividend_stats = {
        'total_stocks': len(symbols),
        'processed': 0,
        'success': 0,
        'failed': 0,
        'new_records': 0,
        'updated_records': 0
    }
    
    for idx, symbol in enumerate(symbols, 1):
        try:
            # 显示进度
            if idx % 10 == 0:
                progress = idx / len(symbols) * 100
                logger.info(f'进度: {idx}/{len(symbols)} ({progress:.1f}%) - {symbol}')
            
            # 获取股利政策数据
            params = {
                'data_id': symbol,  # FinMind 使用 data_id 而不是 stock_id
                'start_date': start_date
            }
            
            data = api_client.fetch_data('TaiwanStockDividend', params)
            
            if not data:
                dividend_stats['processed'] += 1
                continue
            
            # 验证数据
            valid_data = []
            for record in data:
                # 基本验证
                is_valid, error_msg = validator.validate_dividend_data(record)
                if is_valid:
                    valid_data.append(record)
                elif error_msg:
                    logger.debug(f'{symbol} 数据验证失败: {error_msg}')
            
            if not valid_data:
                dividend_stats['processed'] += 1
                continue
            
            # 插入数据库
            for record in valid_data:
                try:
                    result = db.dividend_detail.update_one(
                        {
                            'stock_id': record.get('stock_id'),
                            'date': record.get('date')
                        },
                        {'$set': record},
                        upsert=True
                    )
                    
                    if result.upserted_id:
                        dividend_stats['new_records'] += 1
                    elif result.modified_count > 0:
                        dividend_stats['updated_records'] += 1
                        
                except Exception as e:
                    logger.warning(f'{symbol} 数据插入失败: {e}')
            
            dividend_stats['success'] += 1
            dividend_stats['processed'] += 1
            
        except Exception as e:
            logger.error(f'{symbol} 下载失败: {e}')
            dividend_stats['failed'] += 1
            dividend_stats['processed'] += 1
            continue
    
    # 下载除权除息结果表 (TaiwanStockDividendResult)
    logger.info(f'\n🔄 开始下载除权除息结果表 (TaiwanStockDividendResult)...')
    
    result_stats = {
        'total_stocks': len(symbols),
        'processed': 0,
        'success': 0,
        'failed': 0,
        'new_records': 0,
        'updated_records': 0
    }
    
    for idx, symbol in enumerate(symbols, 1):
        try:
            # 显示进度
            if idx % 10 == 0:
                progress = idx / len(symbols) * 100
                logger.info(f'进度: {idx}/{len(symbols)} ({progress:.1f}%) - {symbol}')
            
            # 获取除权除息结果数据
            params = {
                'data_id': symbol,  # FinMind 使用 data_id 而不是 stock_id
                'start_date': start_date
            }
            
            data = api_client.fetch_data('TaiwanStockDividendResult', params)
            
            if not data:
                result_stats['processed'] += 1
                continue
            
            # 验证数据
            valid_data = []
            for record in data:
                is_valid, error_msg = validator.validate_dividend_data(record)
                if is_valid:
                    valid_data.append(record)
                elif error_msg:
                    logger.debug(f'{symbol} 数据验证失败: {error_msg}')
            
            if not valid_data:
                result_stats['processed'] += 1
                continue
            
            # 插入数据库
            for record in valid_data:
                try:
                    result = db.dividend_results.update_one(
                        {
                            'stock_id': record.get('stock_id'),
                            'date': record.get('date')
                        },
                        {'$set': record},
                        upsert=True
                    )
                    
                    if result.upserted_id:
                        result_stats['new_records'] += 1
                    elif result.modified_count > 0:
                        result_stats['updated_records'] += 1
                        
                except Exception as e:
                    logger.warning(f'{symbol} 数据插入失败: {e}')
            
            result_stats['success'] += 1
            result_stats['processed'] += 1
            
        except Exception as e:
            logger.error(f'{symbol} 下载失败: {e}')
            result_stats['failed'] += 1
            result_stats['processed'] += 1
            continue
    
    # 显示最终统计
    logger.info('\n' + '='*80)
    logger.info('下载完成统计')
    logger.info('='*80)
    
    logger.info(f'\n📊 股利政策表 (dividend_detail):')
    logger.info(f'  处理股票: {dividend_stats["processed"]:,} 档')
    logger.info(f'  成功: {dividend_stats["success"]:,} 档')
    logger.info(f'  失败: {dividend_stats["failed"]:,} 档')
    logger.info(f'  新增记录: {dividend_stats["new_records"]:,} 笔')
    logger.info(f'  更新记录: {dividend_stats["updated_records"]:,} 笔')
    
    logger.info(f'\n📊 除权除息结果表 (dividend_results):')
    logger.info(f'  处理股票: {result_stats["processed"]:,} 档')
    logger.info(f'  成功: {result_stats["success"]:,} 档')
    logger.info(f'  失败: {result_stats["failed"]:,} 档')
    logger.info(f'  新增记录: {result_stats["new_records"]:,} 笔')
    logger.info(f'  更新记录: {result_stats["updated_records"]:,} 笔')
    
    # 检查最终状态
    final_count = db.dividend_results.count_documents({})
    final_stocks = len(db.dividend_results.distinct('symbol'))
    
    logger.info(f'\n📈 最终状态:')
    logger.info(f'  股利记录: {current_count:,} → {final_count:,} 笔 (+{final_count-current_count:,})')
    logger.info(f'  覆盖股票: {current_stocks} → {final_stocks} 档 (+{final_stocks-current_stocks})')
    logger.info(f'  覆盖率: {current_stocks/len(symbols)*100:.2f}% → {final_stocks/len(symbols)*100:.2f}%')
    
    # 评估结果
    if final_stocks / len(symbols) >= 0.90:
        logger.info(f'\n✅ 目标达成！覆盖率超过 90%')
    elif final_stocks / len(symbols) >= 0.70:
        logger.info(f'\n⚠️ 部分达成，覆盖率 70-90%，建议检查失败股票')
    else:
        logger.info(f'\n❌ 未达目标，覆盖率低于 70%，需要重新检查')
    
    # 显示 API 使用情况
    api_usage = api_client.get_api_usage()
    logger.info(f'\n📊 API 使用情况:')
    logger.info(f'  总调用次数: {api_usage["total_calls"]}')
    logger.info(f'  配额限制: {api_usage["quota_per_hour"]} 次/小时')
    logger.info(f'  剩余配额: {api_usage["remaining_quota"]} 次')
    
    mongo_client.close()
    
    logger.info(f'\n🎉 股利数据补充完成！')


def main():
    """主函数"""
    # 获取 API Token
    api_token = os.environ.get('FINMIND_API_TOKEN')
    
    if not api_token:
        print("❌ 错误: 未找到 FINMIND_API_TOKEN 环境变量")
        print("\n请设置环境变量:")
        print("  export FINMIND_API_TOKEN='your_token_here'")
        print("\n或在命令中指定:")
        print("  FINMIND_API_TOKEN='your_token' python3 scripts/补充股利数据.py")
        sys.exit(1)
    
    # 执行下载
    try:
        download_dividend_data(
            api_token=api_token,
            start_date="2015-01-01"  # 从 2015 年开始下载
        )
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断下载")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
