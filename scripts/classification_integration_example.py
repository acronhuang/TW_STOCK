#!/usr/bin/env python3
"""
股票分类系统集成示例

展示如何将 StockClassifier 集成到现有下载流程中
"""

import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import logging
from pymongo import MongoClient

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from utils.stock_classifier import StockClassifier, SecurityType

# 设置 logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 数据库连接
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']


class SmartDownloader:
    """
    智能下载器示例
    
    根据证券类型自动决定需要下载的数据类型
    """
    
    def __init__(self):
        self.classifier = StockClassifier(db)
        self.stats = {
            'total': 0,
            'skipped': 0,
            'downloaded': 0,
            'by_type': {}
        }
    
    def download_financial_statements(self, stock_id: str) -> bool:
        """
        下载财报数据（带分类判断）
        
        Args:
            stock_id: 股票代码
            
        Returns:
            是否执行了下载
        """
        # 获取证券类型
        stock_type = self.classifier.get_type_from_db(stock_id)
        
        # 判断是否需要下载
        if not StockClassifier.should_download_financials(stock_type):
            logger.info(f"⏭️  跳过 {stock_id}: {stock_type.value} 不需要财报数据")
            self.stats['skipped'] += 1
            return False
        
        # 执行下载
        logger.info(f"📥 下载 {stock_id} ({stock_type.value}) 的财报数据...")
        self.stats['downloaded'] += 1
        self.stats['total'] += 1
        
        # 统计
        if stock_type.value not in self.stats['by_type']:
            self.stats['by_type'][stock_type.value] = 0
        self.stats['by_type'][stock_type.value] += 1
        
        # TODO: 实际下载逻辑
        # await self.finmind_service.download_financial_statements(stock_id)
        
        return True
    
    def download_price_data(self, stock_id: str) -> bool:
        """下载股价数据（带分类判断）"""
        stock_type = self.classifier.get_type_from_db(stock_id)
        
        if not StockClassifier.should_download_price(stock_type):
            logger.info(f"⏭️  跳过 {stock_id}: {stock_type.value} 不需要股价数据")
            self.stats['skipped'] += 1
            return False
        
        logger.info(f"📥 下载 {stock_id} ({stock_type.value}) 的股价数据...")
        self.stats['downloaded'] += 1
        self.stats['total'] += 1
        
        return True
    
    def download_dividends(self, stock_id: str) -> bool:
        """下载股利数据（带分类判断）"""
        stock_type = self.classifier.get_type_from_db(stock_id)
        
        if not StockClassifier.should_download_dividends(stock_type):
            logger.info(f"⏭️  跳过 {stock_id}: {stock_type.value} 不需要股利数据")
            self.stats['skipped'] += 1
            return False
        
        logger.info(f"📥 下载 {stock_id} ({stock_type.value}) 的股利数据...")
        self.stats['downloaded'] += 1
        self.stats['total'] += 1
        
        return True
    
    def download_per_pbr(self, stock_id: str) -> bool:
        """下载本益比数据（带分类判断）"""
        stock_type = self.classifier.get_type_from_db(stock_id)
        
        if not StockClassifier.should_download_per_pbr(stock_type):
            logger.info(f"⏭️  跳过 {stock_id}: {stock_type.value} 不需要本益比数据")
            self.stats['skipped'] += 1
            return False
        
        logger.info(f"📥 下载 {stock_id} ({stock_type.value}) 的本益比数据...")
        self.stats['downloaded'] += 1
        self.stats['total'] += 1
        
        return True
    
    def print_stats(self):
        """打印统计信息"""
        print("\n" + "="*80)
        print("📊 下载统计")
        print("="*80)
        print(f"总请求数: {self.stats['total']}")
        print(f"已下载: {self.stats['downloaded']}")
        print(f"已跳过: {self.stats['skipped']}")
        
        if self.stats['total'] > 0:
            skip_rate = self.stats['skipped'] / self.stats['total'] * 100
            print(f"跳过率: {skip_rate:.1f}%")
        
        if self.stats['by_type']:
            print("\n按类型统计:")
            for sec_type, count in sorted(self.stats['by_type'].items()):
                print(f"  {sec_type}: {count} 支")
        print("="*80 + "\n")


def example_1_basic_classification():
    """示例 1: 基本分类"""
    print("\n" + "="*80)
    print("示例 1: 基本分类")
    print("="*80 + "\n")
    
    classifier = StockClassifier(db)
    
    test_stocks = [
        ('2330', '台积电'),
        ('0050', '元大台湾50'),
        ('1256', '鮮活果汁-KY'),
        ('1101B', '台泥特'),
        ('01004T', '权证')
    ]
    
    for stock_id, name in test_stocks:
        stock_type = classifier.get_type_from_db(stock_id)
        requirements = StockClassifier.get_data_requirements(stock_type)
        
        print(f"股票: {stock_id} ({name})")
        print(f"  类型: {stock_type.value}")
        print(f"  需要数据:")
        for data_type, needed in requirements.items():
            icon = "✅" if needed else "❌"
            print(f"    {icon} {data_type}")
        print()


def example_2_smart_download():
    """示例 2: 智能下载"""
    print("\n" + "="*80)
    print("示例 2: 智能下载")
    print("="*80 + "\n")
    
    downloader = SmartDownloader()
    
    # 测试股票列表
    test_stocks = ['2330', '0050', '1256', '1101B', '01004T']
    
    print("📥 下载财报数据:\n")
    for stock_id in test_stocks:
        downloader.download_financial_statements(stock_id)
    
    print("\n" + "-"*80 + "\n")
    
    print("📥 下载股价数据:\n")
    for stock_id in test_stocks:
        downloader.download_price_data(stock_id)
    
    # 打印统计
    downloader.print_stats()


def example_3_batch_analysis():
    """示例 3: 批量分析"""
    print("\n" + "="*80)
    print("示例 3: 批量分析")
    print("="*80 + "\n")
    
    # 获取所有股票
    stock_list = list(db.stock_price.find({}, {'stock_id': 1}).distinct('stock_id'))
    print(f"📊 总股票数: {len(stock_list)} 支\n")
    
    # 分类
    classifier = StockClassifier(db)
    classified = classifier.classify_stock_list(stock_list)
    
    # 统计每种类型需要下载的数据
    print("【各类型数据需求】")
    print("-"*80)
    
    for sec_type, stocks in classified.items():
        if not stocks:
            continue
        
        count = len(stocks)
        percentage = count / len(stock_list) * 100
        
        print(f"\n{sec_type.value}: {count} 支 ({percentage:.1f}%)")
        
        requirements = StockClassifier.get_data_requirements(sec_type)
        needed_data = [k for k, v in requirements.items() if v]
        
        if needed_data:
            print(f"  需要: {', '.join(needed_data)}")
        else:
            print("  需要: (无)")


def example_4_download_plan():
    """示例 4: 生成下载计划"""
    print("\n" + "="*80)
    print("示例 4: 生成下载计划")
    print("="*80 + "\n")
    
    # 获取所有股票
    stock_list = list(db.stock_price.find({}, {'stock_id': 1}).distinct('stock_id'))
    
    # 分类
    classifier = StockClassifier(db)
    classified = classifier.classify_stock_list(stock_list)
    
    # 按数据类型生成下载列表
    data_types = [
        'price',
        'financials',
        'dividends',
        'outstanding_shares',
        'per_pbr',
        'institutional_holdings',
        'margin_trading'
    ]
    
    data_type_names = {
        'price': '股价数据',
        'financials': '财报数据',
        'dividends': '股利数据',
        'outstanding_shares': '流通股数',
        'per_pbr': '本益比',
        'institutional_holdings': '三大法人',
        'margin_trading': '融资融券'
    }
    
    for data_type in data_types:
        download_list = []
        
        for sec_type, stocks in classified.items():
            requirements = StockClassifier.get_data_requirements(sec_type)
            if requirements.get(data_type, False):
                download_list.extend(stocks)
        
        percentage = len(download_list) / len(stock_list) * 100
        
        print(f"📥 {data_type_names.get(data_type, data_type)}")
        print(f"   需要下载: {len(download_list)} 支 ({percentage:.1f}%)")
        print(f"   跳过: {len(stock_list) - len(download_list)} 支")
        print()


def main():
    """主函数"""
    print("\n" + "="*80)
    print("🚀 股票分类系统集成示例")
    print("="*80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    try:
        # 示例 1: 基本分类
        example_1_basic_classification()
        
        # 示例 2: 智能下载
        example_2_smart_download()
        
        # 示例 3: 批量分析
        example_3_batch_analysis()
        
        # 示例 4: 生成下载计划
        example_4_download_plan()
        
        print("\n" + "="*80)
        print("✅ 所有示例执行完成")
        print("="*80 + "\n")
        
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
