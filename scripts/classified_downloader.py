#!/usr/bin/env python3
"""
基于股票分类的智能下载器
根据证券类型自动选择需要下载的数据类型

Author: GitHub Copilot
Date: 2026-02-24
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging
from pymongo import MongoClient

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

from utils.stock_classifier import StockClassifier, SecurityType


class ClassifiedDownloader:
    """基于分类的下载器"""
    
    def __init__(
        self,
        api_token: str,
        db_name: str = 'tw_stock_analysis',
        logger: Optional[logging.Logger] = None
    ):
        """初始化"""
        self.api_token = api_token
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client[db_name]
        self.logger = logger or self._setup_logger()
        self.classifier = StockClassifier(self.db)
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def analyze_stock_list(self, stock_ids: Optional[List[str]] = None) -> Dict:
        """
        分析股票列表，按类型分类并统计数据需求
        
        Args:
            stock_ids: 股票代码列表，None时从数据库获取
            
        Returns:
            Dict: 分类统计结果
        """
        # 获取股票列表
        if stock_ids is None:
            stock_ids = self.db.stock_price.distinct('stock_id')
            self.logger.info(f"📊 从数据库获取股票列表: {len(stock_ids)} 支")
        
        # 分类
        self.logger.info("🔍 正在分类股票...")
        classified = self.classifier.classify_stock_list(stock_ids)
        
        # 统计
        stats = {
            'classification': {},
            'data_requirements': {
                'price': [],
                'financials': [],
                'dividends': [],
                'outstanding_shares': [],
                'per_pbr': [],
                'institutional_holdings': [],
                'margin_trading': []
            }
        }
        
        for sec_type, symbols in classified.items():
            if not symbols or sec_type == SecurityType.UNKNOWN:
                continue
            
            stats['classification'][sec_type.value] = {
                'count': len(symbols),
                'symbols': symbols
            }
            
            # 统计数据需求
            requirements = self.classifier.get_data_requirements(sec_type)
            for data_type, needed in requirements.items():
                if needed:
                    stats['data_requirements'][data_type].extend(symbols)
        
        return stats
    
    def print_classification_report(self, stats: Dict):
        """打印分类报告"""
        print("\n" + "="*80)
        print("📊 股票分类分析报告")
        print("="*80)
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # 分类统计
        print("【证券类型分类】")
        print("-"*80)
        
        total = 0
        for sec_type, info in sorted(stats['classification'].items()):
            count = info['count']
            total += count
            percentage = (count / total * 100) if total > 0 else 0
            
            # 显示样本
            samples = info['symbols'][:5]
            sample_str = ', '.join(samples)
            if len(info['symbols']) > 5:
                sample_str += f", ... (共 {len(info['symbols'])} 支)"
            
            print(f"  {sec_type:20s}: {count:4d} 支 ({percentage:5.1f}%)")
            print(f"    样本: {sample_str}")
        
        print(f"\n  {'总计':20s}: {total:4d} 支")
        print()
        
        # 数据需求统计
        print("【数据下载需求统计】")
        print("-"*80)
        
        for data_type, symbols in sorted(stats['data_requirements'].items()):
            if not symbols:
                continue
            
            count = len(set(symbols))  # 去重
            percentage = (count / total * 100) if total > 0 else 0
            
            print(f"  {data_type:25s}: {count:4d} 支 ({percentage:5.1f}%)")
        
        print()
        print("="*80)
    
    def get_download_list(self, data_type: str, stock_ids: Optional[List[str]] = None) -> List[str]:
        """
        获取指定数据类型的下载列表
        
        Args:
            data_type: 数据类型 (price, financials, dividends, etc.)
            stock_ids: 股票代码列表，None时从数据库获取
            
        Returns:
            List[str]: 需要下载该数据类型的股票列表
        """
        stats = self.analyze_stock_list(stock_ids)
        return sorted(set(stats['data_requirements'].get(data_type, [])))
    
    def print_download_plan(self, stock_ids: Optional[List[str]] = None):
        """
        打印下载计划
        
        Args:
            stock_ids: 股票代码列表，None时从数据库获取
        """
        stats = self.analyze_stock_list(stock_ids)
        self.print_classification_report(stats)
        
        print("\n【下载计划】")
        print("="*80)
        print()
        
        data_types = [
            ('price', '股价数据'),
            ('financials', '财报数据'),
            ('dividends', '股利数据'),
            ('outstanding_shares', '流通股数'),
            ('per_pbr', '本益比/股价净值比'),
            ('institutional_holdings', '三大法人持股'),
            ('margin_trading', '融资融券')
        ]
        
        for data_type, name in data_types:
            symbols = stats['data_requirements'].get(data_type, [])
            if not symbols:
                continue
            
            unique_count = len(set(symbols))
            
            # 按类型统计
            type_breakdown = {}
            classified = self.classifier.classify_stock_list(symbols)
            for sec_type, type_symbols in classified.items():
                if type_symbols and sec_type != SecurityType.UNKNOWN:
                    type_breakdown[sec_type.value] = len(type_symbols)
            
            print(f"📥 {name}")
            print(f"   需要下载: {unique_count} 支")
            
            if type_breakdown:
                breakdown_str = ', '.join([f"{k}: {v}支" for k, v in sorted(type_breakdown.items())])
                print(f"   分布: {breakdown_str}")
            
            print()
        
        print("="*80)


def main():
    """主函数"""
    import os
    
    # 获取 API token
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 错误: 未设置 FINMIND_API_TOKEN 环境变量")
        return
    
    # 创建下载器
    downloader = ClassifiedDownloader(api_token)
    
    # 分析并打印报告
    downloader.print_download_plan()
    
    # 示例：获取需要下载财报的股票列表
    print("\n【示例：财报下载列表】")
    print("="*80)
    financial_stocks = downloader.get_download_list('financials')
    print(f"需要下载财报的股票: {len(financial_stocks)} 支")
    print(f"前 20 支: {', '.join(financial_stocks[:20])}")
    print("="*80)


if __name__ == '__main__':
    main()
