#!/usr/bin/env python3
"""
Factor Library 模組 - 因子庫統一介面

提供統一的因子計算和存儲介面，整合所有因子類別
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

import pandas as pd
from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.factors.value_factors import ValueFactors
from src.factors.momentum_factors import MomentumFactors
from src.factors.quality_factors import QualityFactors
from src.factors.volume_factors import VolumeFactors


class FactorLibrary:
    """
    因子庫統一介面
    
    使用方式:
    ```python
    from src.factors import FactorLibrary
    
    # 建立因子庫
    factor_lib = FactorLibrary()
    
    # 計算並存儲因子
    factor_lib.calculate_and_store(
        symbols=['2330', '2317'],
        start_date='2024-01-01',
        end_date='2024-12-31',
        factor_types=['value', 'momentum', 'quality']
    )
    
    # 查詢因子
    factors = factor_lib.get_factors(
        symbol='2330',
        start_date='2024-01-01',
        end_date='2024-12-31'
    )
    ```
    """
    
    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis",
                 collection_name: str = "stock_factors"):
        """
        初始化因子庫
        
        Args:
            mongo_uri: MongoDB 連接字串
            db_name: 資料庫名稱
            collection_name: 因子集合名稱
        """
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        
        # 因子計算器
        self.value_factors = ValueFactors(self.db)
        self.momentum_factors = MomentumFactors(self.db)
        self.quality_factors = QualityFactors(self.db)
        self.volume_factors = VolumeFactors(self.db)
        
        # 確保索引
        self._ensure_indexes()
        
        # 日誌
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """設定日誌"""
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        logger.addHandler(console_handler)
        
        return logger
    
    def _ensure_indexes(self):
        """建立索引"""
        # 複合索引：symbol + date（唯一）
        self.collection.create_index([('symbol', 1), ('date', -1)], unique=True)
        
        # 單獨索引
        self.collection.create_index([('date', -1)])
        self.collection.create_index([('symbol', 1)])
    
    def calculate_all_factors(self, symbol: str, date: datetime) -> Dict:
        """
        計算單一股票在指定日期的所有因子
        
        Args:
            symbol: 股票代碼
            date: 計算日期
        
        Returns:
            包含所有因子的字典
        """
        # 基本資訊
        factors = {
            'symbol': symbol,
            'date': date,
            'updated_at': datetime.now()
        }
        
        # 價值因子
        value = self.value_factors.calculate_all_value_factors(symbol, date)
        factors.update({k: v for k, v in value.items() if k not in ['symbol', 'date']})
        
        # 動能因子
        momentum = self.momentum_factors.calculate_all_momentum_factors(symbol, date)
        factors.update({k: v for k, v in momentum.items() if k not in ['symbol', 'date']})
        
        # 質量因子
        quality = self.quality_factors.calculate_all_quality_factors(symbol, date)
        factors.update({k: v for k, v in quality.items() if k not in ['symbol', 'date']})

        # 量價因子
        volume = self.volume_factors.calculate_all_volume_factors(symbol, date)
        factors.update({k: v for k, v in volume.items() if k not in ['symbol', 'date']})

        return factors
    
    def calculate_and_store(self,
                           symbols: List[str],
                           start_date: str,
                           end_date: str,
                           factor_types: Optional[List[str]] = None,
                           batch_size: int = 100) -> Dict:
        """
        批次計算並存儲因子
        
        Args:
            symbols: 股票代碼列表
            start_date: 開始日期 (YYYY-MM-DD)
            end_date: 結束日期 (YYYY-MM-DD)
            factor_types: 因子類別列表 ['value', 'momentum', 'quality']，None 表示全部
            batch_size: 批次大小
        
        Returns:
            執行統計 {processed, inserted, updated, failed}
        """
        self.logger.info(f"開始計算因子: {len(symbols)} 支股票")
        self.logger.info(f"日期範圍: {start_date} ~ {end_date}")
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # 取得交易日
        trading_dates = self.db.stock_price.distinct('date', {
            'date': {'$gte': start_dt, '$lte': end_dt}
        })
        trading_dates = sorted(trading_dates)
        
        self.logger.info(f"交易日數: {len(trading_dates)} 天")
        
        # 統計
        stats = {
            'processed': 0,
            'inserted': 0,
            'updated': 0,
            'failed': 0
        }
        
        # 批次處理
        updates = []
        
        for date in trading_dates:
            for symbol in symbols:
                try:
                    # 計算因子
                    factors = {}
                    factors['symbol'] = symbol
                    factors['date'] = date
                    factors['updated_at'] = datetime.now()
                    
                    # 根據指定類別計算
                    if factor_types is None or 'value' in factor_types:
                        value = self.value_factors.calculate_all_value_factors(symbol, date)
                        factors.update({k: v for k, v in value.items() if k not in ['symbol', 'date']})
                    
                    if factor_types is None or 'momentum' in factor_types:
                        momentum = self.momentum_factors.calculate_all_momentum_factors(symbol, date)
                        factors.update({k: v for k, v in momentum.items() if k not in ['symbol', 'date']})
                    
                    if factor_types is None or 'quality' in factor_types:
                        quality = self.quality_factors.calculate_all_quality_factors(symbol, date)
                        factors.update({k: v for k, v in quality.items() if k not in ['symbol', 'date']})

                    if factor_types is None or 'volume' in factor_types:
                        volume = self.volume_factors.calculate_all_volume_factors(symbol, date)
                        factors.update({k: v for k, v in volume.items() if k not in ['symbol', 'date']})

                    # 準備更新操作
                    # 排除 None 值避免覆蓋其他來源的有效資料
                    # 排除 TWSE 管理的欄位避免覆蓋官方 PER/PBR/殖利率
                    _TWSE_MANAGED = {'pe_ratio', 'pb_ratio', 'dividend_yield',
                                     'earnings_yield', 'data_source'}
                    set_fields = {
                        k: v for k, v in factors.items()
                        if v is not None and k not in _TWSE_MANAGED
                    }
                    if set_fields:
                        updates.append(
                            UpdateOne(
                                {'symbol': symbol, 'date': date},
                                {'$set': set_fields},
                                upsert=True
                            )
                        )
                    
                    stats['processed'] += 1
                    
                    # 批次寫入
                    if len(updates) >= batch_size:
                        result = self.collection.bulk_write(updates, ordered=False)
                        stats['inserted'] += result.upserted_count
                        stats['updated'] += result.modified_count
                        updates = []
                        
                        self.logger.info(f"進度: {stats['processed']} / {len(symbols) * len(trading_dates)}")
                
                except Exception as e:
                    self.logger.error(f"計算失敗 {symbol} @ {date}: {e}")
                    stats['failed'] += 1
        
        # 寫入剩餘數據
        if updates:
            result = self.collection.bulk_write(updates, ordered=False)
            stats['inserted'] += result.upserted_count
            stats['updated'] += result.modified_count
        
        self.logger.info(f"計算完成: {stats}")
        return stats
    
    def get_factors(self,
                    symbol: str,
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> pd.DataFrame:
        """
        查詢因子數據
        
        Args:
            symbol: 股票代碼
            start_date: 開始日期（可選）
            end_date: 結束日期（可選）
        
        Returns:
            DataFrame with factors
        """
        query = {'symbol': symbol}
        
        if start_date or end_date:
            query['date'] = {}
            if start_date:
                query['date']['$gte'] = pd.to_datetime(start_date)
            if end_date:
                query['date']['$lte'] = pd.to_datetime(end_date)
        
        cursor = self.collection.find(query).sort('date', 1)
        
        records = []
        for doc in cursor:
            # 移除 MongoDB 內部欄位
            doc.pop('_id', None)
            doc.pop('updated_at', None)
            records.append(doc)
        
        return pd.DataFrame(records)
    
    def get_cross_section(self, date: str, factor_names: Optional[List[str]] = None) -> pd.DataFrame:
        """
        取得橫斷面因子數據（某一天所有股票的因子值）
        
        Args:
            date: 日期 (YYYY-MM-DD)
            factor_names: 因子名稱列表（可選，None 表示全部）
        
        Returns:
            DataFrame with cross-sectional factors
        """
        query = {'date': pd.to_datetime(date)}
        
        # 指定投影欄位
        projection = {'_id': 0, 'symbol': 1, 'date': 1}
        if factor_names:
            for name in factor_names:
                projection[name] = 1
        
        cursor = self.collection.find(query, projection)
        
        return pd.DataFrame(list(cursor))
    
    def calculate_factor_stats(self, factor_name: str, start_date: str, end_date: str) -> Dict:
        """
        計算因子統計量
        
        Args:
            factor_name: 因子名稱
            start_date: 開始日期
            end_date: 結束日期
        
        Returns:
            {mean, median, std, min, max, coverage}
        """
        pipeline = [
            {
                '$match': {
                    'date': {
                        '$gte': pd.to_datetime(start_date),
                        '$lte': pd.to_datetime(end_date)
                    },
                    factor_name: {'$exists': True, '$ne': None}
                }
            },
            {
                '$group': {
                    '_id': None,
                    'mean': {'$avg': f'${factor_name}'},
                    'min': {'$min': f'${factor_name}'},
                    'max': {'$max': f'${factor_name}'},
                    'count': {'$sum': 1}
                }
            }
        ]
        
        result = list(self.collection.aggregate(pipeline))
        
        if not result:
            return None
        
        stats = result[0]
        stats.pop('_id')
        
        # 計算覆蓋率
        total_records = self.collection.count_documents({
            'date': {
                '$gte': pd.to_datetime(start_date),
                '$lte': pd.to_datetime(end_date)
            }
        })
        
        stats['coverage'] = (stats['count'] / total_records * 100) if total_records > 0 else 0
        
        return stats
    
    def list_available_factors(self) -> List[str]:
        """
        列出所有可用的因子名稱
        
        Returns:
            因子名稱列表
        """
        sample = self.collection.find_one()
        
        if not sample:
            return []
        
        # 排除系統欄位
        exclude = ['_id', 'symbol', 'date', 'updated_at']
        
        return [k for k in sample.keys() if k not in exclude]
