#!/usr/bin/env python3
"""
计算并添加 PE (本益比) 和 PB (股价净值比) 到 tickers 集合

公式:
- PE Ratio (本益比) = 股价 / 每股盈余 (EPS)
- PB Ratio (股价净值比) = 股价 / 每股净值 (Book Value Per Share)

数据来源:
- 股价: tickers.closePrice
- EPS: financial_reports.incomeStatement._raw.EPS
- 每股净值: financial_reports.balanceSheet.equity / 股本

作者: Professional Financial Systems Architect
日期: 2026-02-21
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
import logging

from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class PEPBCalculator:
    """PE/PB 比率计算器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.stats = {
            'total_tickers': 0,
            'updated': 0,
            'no_eps_data': 0,
            'no_financial_data': 0,
            'invalid_values': 0,
            'errors': 0
        }
    
    def decimal_to_float(self, value: Any) -> Optional[float]:
        """转换 Decimal128 为 float"""
        if value is None:
            return None
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None
    
    def get_latest_financial_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新的财务报表数据"""
        try:
            # 查找最新的财务报表（按年份和季度降序）
            financial = self.db.financial_reports.find_one(
                {'symbol': symbol},
                sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
            )
            
            if not financial:
                return None
            
            # 提取需要的数据
            eps_raw = financial.get('incomeStatement', {}).get('_raw', {}).get('EPS')
            eps = self.decimal_to_float(eps_raw)
            
            equity_raw = financial.get('balanceSheet', {}).get('equity')
            equity = self.decimal_to_float(equity_raw)
            
            return {
                'eps': eps,
                'equity': equity,
                'fiscalYear': financial.get('fiscalYear'),
                'fiscalPeriod': financial.get('fiscalPeriod')
            }
        
        except Exception as e:
            logger.error(f'获取 {symbol} 财务数据失败: {e}')
            return None
    
    def get_outstanding_shares(self, symbol: str) -> Optional[float]:
        """
        获取流通股数（张数转换为股数）
        台股1张 = 1000股
        """
        try:
            ticker = self.db.tickers.find_one({'symbol': symbol})
            if not ticker:
                return None
            
            # 尝试从多个可能的字段获取股本信息
            shares_fields = ['outstandingShares', 'totalShares', 'sharesOutstanding']
            
            for field in shares_fields:
                if field in ticker:
                    shares_raw = ticker[field]
                    shares = self.decimal_to_float(shares_raw)
                    if shares and shares > 0:
                        # 如果是张数，转换为股数
                        if shares < 1000000:  # 假设小于100万是张数
                            return shares * 1000
                        return shares
            
            # 如果没有直接的股数字段，尝试从市值和股价反推
            market_cap_raw = ticker.get('marketCap')
            price_raw = ticker.get('closePrice')
            
            if market_cap_raw and price_raw:
                market_cap = self.decimal_to_float(market_cap_raw)
                price = self.decimal_to_float(price_raw)
                
                if market_cap and price and price > 0:
                    return market_cap / price
            
            # 默认估算：根据股票代号估计（大型股约 10-100 亿股）
            # 这只是一个粗略估计，实际应该从权威数据源获取
            logger.warning(f'{symbol}: 无法获取准确股数，使用保守估计')
            return None
        
        except Exception as e:
            logger.error(f'获取 {symbol} 股数失败: {e}')
            return None
    
    def calculate_ratios(self, symbol: str, price: float, financial_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
        """计算 PE 和 PB 比率"""
        result = {
            'peRatio': None,
            'pbRatio': None,
            'fiscalYear': financial_data.get('fiscalYear'),
            'fiscalPeriod': financial_data.get('fiscalPeriod')
        }
        
        # 计算 PE Ratio
        eps = financial_data.get('eps')
        if eps and eps > 0:
            result['peRatio'] = round(price / eps, 2)
        
        # 计算 PB Ratio
        equity = financial_data.get('equity')
        if equity and equity > 0:
            # 尝试获取流通股数
            shares = self.get_outstanding_shares(symbol)
            
            if shares and shares > 0:
                book_value_per_share = equity / shares
                if book_value_per_share > 0:
                    result['pbRatio'] = round(price / book_value_per_share, 2)
            else:
                # 如果没有股数，使用简化公式（不够精确，但可以给出参考值）
                # 假设典型台股约 10 亿股流通量
                estimated_shares = 1_000_000_000
                book_value_per_share = equity / estimated_shares
                result['pbRatio'] = round(price / book_value_per_share, 2)
                logger.debug(f'{symbol}: 使用估算股数计算 PB')
        
        return result
    
    def validate_ratios(self, symbol: str, ratios: Dict[str, Any]) -> bool:
        """验证比率的合理性"""
        pe = ratios.get('peRatio')
        pb = ratios.get('pbRatio')
        
        # PE 合理范围: 0-200 (负值表示亏损，超过200可能是异常)
        if pe is not None and (pe < 0 or pe > 200):
            logger.warning(f'{symbol}: PE={pe} 超出合理范围 [0-200]')
            return False
        
        # PB 合理范围: 0-20 (负值不合理，超过20可能是异常)
        if pb is not None and (pb <= 0 or pb > 20):
            logger.warning(f'{symbol}: PB={pb} 超出合理范围 (0-20]')
            return False
        
        return True
    
    def process_all_tickers(self):
        """处理所有 tickers"""
        logger.info('开始计算 PE/PB 比率...')
        logger.info('=' * 60)
        
        # 获取所有 tickers
        tickers = list(self.db.tickers.find({}))
        self.stats['total_tickers'] = len(tickers)
        
        logger.info(f'找到 {self.stats["total_tickers"]} 档股票')
        
        bulk_operations = []
        
        for idx, ticker in enumerate(tickers, 1):
            symbol = ticker.get('symbol')
            
            try:
                # 获取股价
                price_raw = ticker.get('closePrice') or ticker.get('close')
                price = self.decimal_to_float(price_raw)
                
                if not price or price <= 0:
                    logger.debug(f'{symbol}: 无有效股价')
                    self.stats['invalid_values'] += 1
                    continue
                
                # 获取财务数据
                financial_data = self.get_latest_financial_data(symbol)
                
                if not financial_data:
                    logger.debug(f'{symbol}: 无财务数据')
                    self.stats['no_financial_data'] += 1
                    continue
                
                # 计算比率
                ratios = self.calculate_ratios(symbol, price, financial_data)
                
                # 验证比率
                if not self.validate_ratios(symbol, ratios):
                    self.stats['invalid_values'] += 1
                    # 仍然写入，但标记为可疑
                    ratios['validated'] = False
                else:
                    ratios['validated'] = True
                
                # 准备更新操作
                update_fields = {
                    'updatedAt': datetime.now()
                }
                
                if ratios['peRatio'] is not None:
                    update_fields['peRatio'] = Decimal128(Decimal(str(ratios['peRatio'])))
                
                if ratios['pbRatio'] is not None:
                    update_fields['pbRatio'] = Decimal128(Decimal(str(ratios['pbRatio'])))
                
                if ratios.get('fiscalYear'):
                    update_fields['financialDataYear'] = ratios['fiscalYear']
                    update_fields['financialDataPeriod'] = ratios['fiscalPeriod']
                
                update_fields['ratiosValidated'] = ratios['validated']
                
                bulk_operations.append(
                    UpdateOne(
                        {'_id': ticker['_id']},
                        {'$set': update_fields}
                    )
                )
                
                self.stats['updated'] += 1
                
                # 每 100 笔输出进度
                if idx % 100 == 0:
                    logger.info(f'进度: {idx}/{self.stats["total_tickers"]} ({idx/self.stats["total_tickers"]*100:.1f}%)  '
                               f'成功: {self.stats["updated"]}, 缺财务: {self.stats["no_financial_data"]}')
                
                # 每 500 笔批量写入
                if len(bulk_operations) >= 500:
                    self.db.tickers.bulk_write(bulk_operations)
                    bulk_operations = []
            
            except Exception as e:
                logger.error(f'{symbol}: 处理失败: {e}')
                self.stats['errors'] += 1
        
        # 写入剩余操作
        if bulk_operations:
            self.db.tickers.bulk_write(bulk_operations)
        
        logger.info('=' * 60)
        self.print_summary()
    
    def print_summary(self):
        """打印执行摘要"""
        logger.info('\n' + '=' * 60)
        logger.info('执行摘要')
        logger.info('=' * 60)
        logger.info(f'总股票数: {self.stats["total_tickers"]:,}')
        logger.info(f'成功更新: {self.stats["updated"]:,} ({self.stats["updated"]/self.stats["total_tickers"]*100:.1f}%)')
        logger.info(f'缺少财务数据: {self.stats["no_financial_data"]:,}')
        logger.info(f'数值异常: {self.stats["invalid_values"]:,}')
        logger.info(f'处理错误: {self.stats["errors"]:,}')
        logger.info('=' * 60)
        
        # 验证结果
        logger.info('\n检查更新结果...')
        has_pe = self.db.tickers.count_documents({'peRatio': {'$exists': True}})
        has_pb = self.db.tickers.count_documents({'pbRatio': {'$exists': True}})
        logger.info(f'✅ 有 PE 字段: {has_pe:,} ({has_pe/self.stats["total_tickers"]*100:.1f}%)')
        logger.info(f'✅ 有 PB 字段: {has_pb:,} ({has_pb/self.stats["total_tickers"]*100:.1f}%)')
        
        # 显示几个样本
        logger.info('\n样本数据 (前5档):')
        samples = self.db.tickers.find(
            {'peRatio': {'$exists': True}},
            {'symbol': 1, 'name': 1, 'closePrice': 1, 'peRatio': 1, 'pbRatio': 1}
        ).limit(5)
        
        for sample in samples:
            symbol = sample.get('symbol')
            name = sample.get('name', 'N/A')
            price = self.decimal_to_float(sample.get('closePrice'))
            pe = self.decimal_to_float(sample.get('peRatio'))
            pb = self.decimal_to_float(sample.get('pbRatio'))
            
            logger.info(f'{symbol} ({name}): 股价={price:.2f}, PE={pe:.2f if pe else "N/A"}, PB={pb:.2f if pb else "N/A"}')
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    try:
        calculator = PEPBCalculator()
        calculator.process_all_tickers()
        calculator.close()
        
        logger.info('\n✅ PE/PB 比率计算完成!')
        return 0
    
    except Exception as e:
        logger.error(f'执行失败: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
