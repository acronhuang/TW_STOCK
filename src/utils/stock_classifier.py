#!/usr/bin/env python3
"""
股票分类管理器
根据证券类型进行分类并管理不同的数据下载需求

Author: GitHub Copilot
Date: 2026-02-24
"""

from typing import Dict, List, Set
from enum import Enum
import re
from pymongo import MongoClient


class SecurityType(Enum):
    """证券类型枚举"""
    STOCK = "Stock"                    # 正常股票
    ETF = "ETF"                        # ETF基金
    KY_STOCK = "KY-Stock"              # KY股（海外注册）
    PREFERRED_STOCK = "PreferredStock" # 特别股
    WARRANT = "Warrant"                # 权证
    DR = "DR"                          # 存托凭证
    UNKNOWN = "Unknown"                # 未知类型


class StockClassifier:
    """股票分类器"""
    
    def __init__(self, db_connection=None):
        """初始化分类器"""
        self.db = db_connection
    
    @staticmethod
    def classify_by_code(stock_id: str, stock_name: str = "") -> SecurityType:
        """
        根据股票代码和名称判断证券类型
        
        规则：
        1. ETF: 00开头（0050, 006208, 00633L等）
        2. 权证: 5位数+T（01004T）
        3. KY股: 股票名称含"-KY"
        4. 特别股: 股票代码含字母且非ETF/权证（1101B, 1312A）
        5. 存托凭证: 股票代码含"DR"
        6. 正常股票: 4位数字，1-9开头
        
        Args:
            stock_id: 股票代码
            stock_name: 股票名称（可选）
            
        Returns:
            SecurityType 枚举值
        """
        if not stock_id:
            return SecurityType.UNKNOWN
        
        # ETF: 00开头（4位数字、6位数字、或带字母后缀）
        if re.match(r'^00\d{2}$', stock_id):  # 0050, 0051, 0056
            return SecurityType.ETF
        if re.match(r'^00\d{4}$', stock_id):  # 006208
            return SecurityType.ETF
        if re.match(r'^00\d{3}[A-Z]$', stock_id):  # 00633L, 00634R
            return SecurityType.ETF
        
        # 权证: 5位数+T
        if re.match(r'^\d{5}T$', stock_id):
            return SecurityType.WARRANT
        
        # 存托凭证: 含DR
        if 'DR' in stock_id.upper():
            return SecurityType.DR
        
        # KY股: 名称含-KY
        if stock_name and '-KY' in stock_name:
            return SecurityType.KY_STOCK
        
        # 特别股: 4位数+字母（非ETF格式）
        if re.match(r'^\d{4}[A-Z]$', stock_id):
            return SecurityType.PREFERRED_STOCK
        
        # 正常股票: 4位数字，1-9开头
        if re.match(r'^[1-9]\d{3}$', stock_id):
            return SecurityType.STOCK
        
        return SecurityType.UNKNOWN
    
    def get_type_from_db(self, stock_id: str) -> SecurityType:
        """
        从数据库获取证券类型
        
        策略:
        1. 优先使用代码规则判断（ETF、权证等明显特征）
        2. 如果代码规则返回正常股票或未知，再查数据库
        3. 这样可以修正数据库中的错误分类
        
        Args:
            stock_id: 股票代码
            
        Returns:
            SecurityType 枚举值
        """
        if self.db is None:
            return SecurityType.UNKNOWN
        
        # 先用代码规则判断
        code_type = self.classify_by_code(stock_id)
        
        # 如果代码规则明确识别出非 Stock/Unknown 类型，直接返回
        if code_type not in [SecurityType.STOCK, SecurityType.UNKNOWN]:
            return code_type
        
        # 查询数据库
        info = self.db.taiwan_stock_info.find_one({'stock_id': stock_id})
        
        if not info:
            # 数据库中没有记录，返回代码规则的结果
            return code_type
        
        # 如果有 security_type 字段且合法
        if 'security_type' in info:
            try:
                db_type = SecurityType(info['security_type'])
                # 如果代码规则已经是 STOCK，使用数据库的判断（可能是 KY 股等）
                if code_type == SecurityType.STOCK:
                    return db_type
            except ValueError:
                pass
        
        # 根据股票名称判断 KY 股
        stock_name = info.get('stock_name', '')
        if stock_name and '-KY' in stock_name:
            return SecurityType.KY_STOCK
        
        # 返回代码规则的判断结果
        return code_type
    
    def classify_stock_list(self, stock_ids: List[str]) -> Dict[SecurityType, List[str]]:
        """
        将股票列表按类型分类
        
        Args:
            stock_ids: 股票代码列表
            
        Returns:
            Dict[SecurityType, List[str]]: 按类型分类的股票字典
        """
        classified = {st: [] for st in SecurityType}
        
        for stock_id in stock_ids:
            if self.db is not None:
                sec_type = self.get_type_from_db(stock_id)
            else:
                sec_type = self.classify_by_code(stock_id)
            
            classified[sec_type].append(stock_id)
        
        return classified
    
    @staticmethod
    def should_download_financials(sec_type: SecurityType) -> bool:
        """
        判断该证券类型是否应下载财报数据
        
        Args:
            sec_type: 证券类型
            
        Returns:
            bool: 是否应下载财报
        """
        # 只有正常股票、KY股、特别股需要下载财报
        return sec_type in {
            SecurityType.STOCK,
            SecurityType.KY_STOCK,
            SecurityType.PREFERRED_STOCK
        }
    
    @staticmethod
    def should_download_dividends(sec_type: SecurityType) -> bool:
        """
        判断该证券类型是否应下载股利数据
        
        Args:
            sec_type: 证券类型
            
        Returns:
            bool: 是否应下载股利
        """
        # ETF、正常股票、特别股、KY股都可能有股利
        return sec_type in {
            SecurityType.STOCK,
            SecurityType.ETF,
            SecurityType.KY_STOCK,
            SecurityType.PREFERRED_STOCK
        }
    
    @staticmethod
    def should_download_price(sec_type: SecurityType) -> bool:
        """
        判断该证券类型是否应下载价格数据
        
        Args:
            sec_type: 证券类型
            
        Returns:
            bool: 是否应下载价格
        """
        # 权证生命周期短，一般不需要历史价格
        return sec_type != SecurityType.WARRANT
    
    @staticmethod
    def should_download_outstanding_shares(sec_type: SecurityType) -> bool:
        """
        判断该证券类型是否应下载流通股数
        
        Args:
            sec_type: 证券类型
            
        Returns:
            bool: 是否应下载流通股数
        """
        # 只有正常股票和KY股需要流通股数
        return sec_type in {
            SecurityType.STOCK,
            SecurityType.KY_STOCK,
            SecurityType.PREFERRED_STOCK
        }
    
    @staticmethod
    def should_download_per_pbr(sec_type: SecurityType) -> bool:
        """
        判断该证券类型是否应下载本益比/股价净值比
        
        Args:
            sec_type: 证券类型
            
        Returns:
            bool: 是否应下载 PER/PBR
        """
        # 只有正常股票和KY股需要 PER/PBR
        return sec_type in {
            SecurityType.STOCK,
            SecurityType.KY_STOCK
        }
    
    @staticmethod
    def get_data_requirements(sec_type: SecurityType) -> Dict[str, bool]:
        """
        获取该证券类型的数据需求
        
        Args:
            sec_type: 证券类型
            
        Returns:
            Dict[str, bool]: 数据需求字典
        """
        return {
            'price': StockClassifier.should_download_price(sec_type),
            'financials': StockClassifier.should_download_financials(sec_type),
            'dividends': StockClassifier.should_download_dividends(sec_type),
            'outstanding_shares': StockClassifier.should_download_outstanding_shares(sec_type),
            'per_pbr': StockClassifier.should_download_per_pbr(sec_type),
            'institutional_holdings': sec_type == SecurityType.STOCK,  # 只有正常股票
            'margin_trading': sec_type == SecurityType.STOCK,  # 只有正常股票
        }


def main():
    """测试分类器"""
    classifier = StockClassifier()
    
    test_cases = [
        ('2330', '台积电'),
        ('0050', '元大台湾50'),
        ('006208', '富邦台50'),
        ('00633L', '杠杆ETF'),
        ('01004T', '权证'),
        ('1101B', '台泥特'),
        ('4904', '远传-KY'),  # 假设
        ('2354', '正常股票'),
    ]
    
    print("="*80)
    print("股票分类测试")
    print("="*80)
    
    for stock_id, stock_name in test_cases:
        sec_type = classifier.classify_by_code(stock_id, stock_name)
        requirements = classifier.get_data_requirements(sec_type)
        
        print(f"\n股票代码: {stock_id} ({stock_name})")
        print(f"  类型: {sec_type.value}")
        print(f"  数据需求:")
        for data_type, needed in requirements.items():
            icon = "✅" if needed else "❌"
            print(f"    {icon} {data_type}")
    
    print("\n" + "="*80)


if __name__ == '__main__':
    main()
