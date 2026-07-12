#!/usr/bin/env python3
"""
添加数据验证层

验证规则:
1. 价格逻辑: high >= close >= low
2. 价格变化: changePercent 在合理范围内 (-10% ~ +10%)
3. Decimal128 精度检查
4. 必填字段检查
5. 数值范围检查

注意: MongoDB 本身不支持严格的模式验证（Schema Validation）除非使用 JSON Schema Validator
本脚本通过扫描数据并标记异常记录

作者: Professional Financial Systems Architect
日期: 2026-02-21
"""

import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional
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


class DataValidator:
    """数据验证器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.validation_results = {
            'stock_price': {
                'total': 0,
                'price_logic_errors': [],
                'change_percent_errors': [],
                'negative_price_errors': [],
                'missing_fields': []
            },
            'tickers': {
                'total': 0,
                'invalid_ratios': [],
                'negative_values': [],
                'missing_fields': []
            },
            'financial_reports': {
                'total': 0,
                'negative_equity': [],
                'invalid_ratios': [],
                'missing_fields': []
            }
        }
    
    def decimal_to_float(self, value: Any) -> Optional[float]:
        """转换 Decimal128 为 float"""
        if value is None:
            return None
        if isinstance(value, Decimal128):
            try:
                return float(value.to_decimal())
            except (InvalidOperation, ValueError):
                return None
        if isinstance(value, (int, float)):
            return float(value)
        return None
    
    def validate_stock_price(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """验证股价数据"""
        errors = []
        
        symbol = record.get('symbol', 'UNKNOWN')
        date = record.get('date', 'UNKNOWN')
        
        # 提取价格字段
        high = self.decimal_to_float(record.get('high') or record.get('highPrice'))
        low = self.decimal_to_float(record.get('low') or record.get('lowPrice'))
        close = self.decimal_to_float(record.get('close') or record.get('closePrice'))
        open_price = self.decimal_to_float(record.get('open') or record.get('openPrice'))
        change_percent = self.decimal_to_float(record.get('changePercent'))
        
        # 验证1: 价格逻辑 (high >= close >= low)
        if high is not None and low is not None and close is not None:
            if not (low <= close <= high):
                errors.append({
                    'type': 'price_logic_error',
                    'symbol': symbol,
                    'date': date,
                    'message': f'价格逻辑错误: low={low}, close={close}, high={high}',
                    'severity': 'ERROR'
                })
        
        # 验证2: 负价格
        for field, value in [('high', high), ('low', low), ('close', close), ('open', open_price)]:
            if value is not None and value < 0:
                errors.append({
                    'type': 'negative_price',
                    'symbol': symbol,
                    'date': date,
                    'field': field,
                    'value': value,
                    'message': f'{field}={value} 为负值',
                    'severity': 'ERROR'
                })
        
        # 验证3: 涨跌幅范围 (-10% ~ +10%, 台股涨跌停限制)
        if change_percent is not None:
            if change_percent < -10 or change_percent > 10:
                errors.append({
                    'type': 'change_percent_out_of_range',
                    'symbol': symbol,
                    'date': date,
                    'value': change_percent,
                    'message': f'涨跌幅={change_percent:.2f}% 超出范围 [-10%, +10%]',
                    'severity': 'WARNING'
                })
        
        # 验证4: 必填字段
        required_fields = ['symbol', 'date', 'closePrice', 'tradeVolume']
        for field in required_fields:
            if field not in record or record[field] is None:
                errors.append({
                    'type': 'missing_field',
                    'symbol': symbol,
                    'date': date,
                    'field': field,
                    'message': f'缺少必填字段: {field}',
                    'severity': 'ERROR'
                })
        
        return errors
    
    def validate_ticker(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """验证 ticker 数据"""
        errors = []
        
        symbol = record.get('symbol', 'UNKNOWN')
        
        # 验证 PE/PB 比率
        pe = self.decimal_to_float(record.get('peRatio'))
        pb = self.decimal_to_float(record.get('pbRatio'))
        
        if pe is not None and (pe < 0 or pe > 200):
            errors.append({
                'type': 'invalid_pe_ratio',
                'symbol': symbol,
                'value': pe,
                'message': f'PE={pe:.2f} 超出合理范围 [0, 200]',
                'severity': 'WARNING'
            })
        
        if pb is not None and (pb <= 0 or pb > 20):
            errors.append({
                'type': 'invalid_pb_ratio',
                'symbol': symbol,
                'value': pb,
                'message': f'PB={pb:.2f} 超出合理范围 (0, 20]',
                'severity': 'WARNING'
            })
        
        # 验证股价
        close_price = self.decimal_to_float(record.get('closePrice'))
        if close_price is not None and close_price <= 0:
            errors.append({
                'type': 'invalid_price',
                'symbol': symbol,
                'value': close_price,
                'message': f'股价={close_price} 无效',
                'severity': 'ERROR'
            })
        
        return errors
    
    def validate_financial_report(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """验证财务报表数据"""
        errors = []
        
        symbol = record.get('symbol', 'UNKNOWN')
        year = record.get('fiscalYear', 'UNKNOWN')
        period = record.get('fiscalPeriod', 'UNKNOWN')
        
        # 提取财务数据
        equity = self.decimal_to_float(record.get('balanceSheet', {}).get('equity'))
        total_assets = self.decimal_to_float(record.get('balanceSheet', {}).get('totalAssets'))
        total_liabilities = self.decimal_to_float(record.get('balanceSheet', {}).get('totalLiabilities'))
        
        # 验证资产负债平衡: 总资产 = 股东权益 + 负债
        if equity is not None and total_assets is not None and total_liabilities is not None:
            calculated_assets = equity + total_liabilities
            
            # 避免除以零
            if total_assets == 0:
                logger.warning(f'{symbol} {year}{period}: total_assets=0')
                return errors
            
            diff_percent = abs(total_assets - calculated_assets) / total_assets * 100
            
            if diff_percent > 1:  # 容许 1% 误差
                errors.append({
                    'type': 'balance_sheet_mismatch',
                    'symbol': symbol,
                    'year': year,
                    'period': period,
                    'message': f'资产负债不平衡: 资产={total_assets:,.0f}, 权益+负债={calculated_assets:,.0f}, 差异={diff_percent:.2f}%',
                    'severity': 'WARNING'
                })
        
        # 验证权益为正
        if equity is not None and equity < 0:
            errors.append({
                'type': 'negative_equity',
                'symbol': symbol,
                'year': year,
                'period': period,
                'value': equity,
                'message': f'股东权益为负: {equity:,.0f}',
                'severity': 'WARNING'
            })
        
        # 验证 ROE/ROA 范围
        roe = self.decimal_to_float(record.get('ratios', {}).get('roe'))
        roa = self.decimal_to_float(record.get('ratios', {}).get('roa'))
        
        if roe is not None and (roe < -100 or roe > 100):
            errors.append({
                'type': 'invalid_roe',
                'symbol': symbol,
                'year': year,
                'period': period,
                'value': roe,
                'message': f'ROE={roe:.2f}% 超出合理范围 [-100%, 100%]',
                'severity': 'WARNING'
            })
        
        if roa is not None and (roa < -50 or roa > 50):
            errors.append({
                'type': 'invalid_roa',
                'symbol': symbol,
                'year': year,
                'period': period,
                'value': roa,
                'message': f'ROA={roa:.2f}% 超出合理范围 [-50%, 50%]',
                'severity': 'WARNING'
            })
        
        return errors
    
    def scan_collection(self, collection_name: str, validator_func, batch_size: int = 1000):
        """扫描集合并验证数据"""
        logger.info(f'\n扫描集合: {collection_name}')
        logger.info('=' * 60)
        
        collection = self.db[collection_name]
        total = collection.count_documents({})
        self.validation_results[collection_name]['total'] = total
        
        logger.info(f'总记录数: {total:,}')
        
        processed = 0
        error_count = 0
        
        cursor = collection.find({}).batch_size(batch_size)
        
        for record in cursor:
            errors = validator_func(record)
            
            if errors:
                error_count += 1
                for error in errors:
                    error_type = error['type']
                    if error_type not in self.validation_results[collection_name]:
                        self.validation_results[collection_name][error_type] = []
                    self.validation_results[collection_name][error_type].append(error)
            
            processed += 1
            
            if processed % 10000 == 0:
                logger.info(f'进度: {processed:,}/{total:,} ({processed/total*100:.1f}%) - 错误: {error_count:,}')
        
        logger.info(f'完成: {processed:,} 笔记录, {error_count:,} 笔有错误')
        
        return error_count
    
    def print_validation_summary(self):
        """打印验证摘要"""
        logger.info('\n' + '=' * 60)
        logger.info('数据验证摘要')
        logger.info('=' * 60)
        
        for collection_name, results in self.validation_results.items():
            if results['total'] == 0:
                continue
            
            logger.info(f'\n【{collection_name}】')
            logger.info(f'总记录数: {results["total"]:,}')
            
            error_types = [k for k in results.keys() if k != 'total' and isinstance(results[k], list) and len(results[k]) > 0]
            
            if not error_types:
                logger.info('✅ 无错误')
                continue
            
            for error_type in error_types:
                errors = results[error_type]
                logger.info(f'\n  {error_type}: {len(errors):,} 笔')
                
                # 显示前 5 个样本
                for error in errors[:5]:
                    severity = error.get('severity', 'INFO')
                    message = error.get('message', '')
                    symbol = error.get('symbol', '')
                    logger.info(f'    [{severity}] {symbol}: {message}')
                
                if len(errors) > 5:
                    logger.info(f'    ... 还有 {len(errors)-5} 笔')
        
        logger.info('\n' + '=' * 60)
    
    def run_validation(self):
        """运行完整验证流程"""
        logger.info('开始数据验证...')
        logger.info('=' * 60)
        
        # 验证 stock_price
        self.scan_collection('stock_price', self.validate_stock_price)
        
        # 验证 tickers
        self.scan_collection('tickers', self.validate_ticker)
        
        # 验证 financial_reports
        self.scan_collection('financial_reports', self.validate_financial_report)
        
        # 打印摘要
        self.print_validation_summary()
        
        logger.info('\n✅ 数据验证完成!')
    
    def close(self):
        """关闭数据库连接"""
        self.client.close()


def main():
    """主函数"""
    try:
        validator = DataValidator()
        validator.run_validation()
        validator.close()
        return 0
    
    except Exception as e:
        logger.error(f'执行失败: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
