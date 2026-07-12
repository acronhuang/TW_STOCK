#!/usr/bin/env python3
"""
技術指標計算腳本
==================

從 stock_price 計算技術指標並存入 technical_indicators 集合

技術指標:
- MA5, MA10, MA20, MA60 (移動平均線)
- RSI (相對強弱指標)
- MACD (平滑異同移動平均線)
- KD (隨機指標)
- 布林通道 (Bollinger Bands)
- 成交量移動平均

使用方式:
    python3 calculate_technical_indicators.py --from-date 2025-11-05
    python3 calculate_technical_indicators.py --symbols 2330,2317,2454
    python3 calculate_technical_indicators.py --all  # 計算所有股票
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pymongo import MongoClient, UpdateOne
import logging

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TechnicalIndicatorCalculator:
    """技術指標計算器"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        
    def calculate_ma(self, df, periods=[5, 10, 20, 60]):
        """計算移動平均線"""
        for period in periods:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df
    
    def calculate_rsi(self, df, period=14):
        """計算 RSI"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        """計算 MACD"""
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        return df
    
    def calculate_kd(self, df, period=9):
        """計算 KD 指標"""
        low_min = df['low'].rolling(window=period).min()
        high_max = df['high'].rolling(window=period).max()
        
        df['rsv'] = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['k'] = df['rsv'].ewm(com=2, adjust=False).mean()
        df['d'] = df['k'].ewm(com=2, adjust=False).mean()
        return df
    
    def calculate_bollinger_bands(self, df, period=20, std_dev=2):
        """計算布林通道"""
        df['bb_middle'] = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        df['bb_upper'] = df['bb_middle'] + (std * std_dev)
        df['bb_lower'] = df['bb_middle'] - (std * std_dev)
        return df
    
    def calculate_volume_ma(self, df, periods=[5, 10, 20]):
        """計算成交量移動平均"""
        for period in periods:
            df[f'volume_ma{period}'] = df['volume'].rolling(window=period).mean()
        return df
    
    def calculate_all_indicators(self, df):
        """計算所有技術指標"""
        if len(df) < 60:  # 需要至少 60 天的資料
            logger.warning(f"資料量不足 ({len(df)} 天),需要至少 60 天")
            return None
        
        # 確保資料按日期排序
        df = df.sort_values('date')
        
        # 計算各項指標
        df = self.calculate_ma(df)
        df = self.calculate_rsi(df)
        df = self.calculate_macd(df)
        df = self.calculate_kd(df)
        df = self.calculate_bollinger_bands(df)
        df = self.calculate_volume_ma(df)
        
        return df
    
    def process_symbol(self, symbol, from_date=None):
        """處理單一股票"""
        try:
            # 查詢股價資料
            query = {'symbol': symbol}
            if from_date:
                # 往前多抓 60 天以確保有足夠的資料計算指標
                # 🔧 修正: 保持 datetime 物件,不要轉換成字串
                start_date = pd.to_datetime(from_date) - timedelta(days=60)
                query['date'] = {'$gte': start_date.to_pydatetime()}
            
            cursor = self.db.stock_price.find(query).sort('date', 1)
            data = list(cursor)
            
            if not data:
                logger.warning(f"❌ {symbol}: 沒有股價資料")
                return 0
            
            # 轉換為 DataFrame
            df = pd.DataFrame(data)
            
            # 確保 date 欄位是 datetime 類型
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            # 計算技術指標
            df = self.calculate_all_indicators(df)
            
            if df is None:
                return 0
            
            # 過濾出需要更新的日期
            if from_date:
                # 確保 from_date 也是 datetime 類型
                from_date_dt = pd.to_datetime(from_date)
                df = df[df['date'] >= from_date_dt]
            
            # 準備批次更新
            bulk_operations = []
            
            for _, row in df.iterrows():
                # 跳過有 NaN 的資料
                if row.isnull().any():
                    continue
                
                doc = {
                    'symbol': symbol,
                    'date': row['date'],
                    'ma5': float(row['ma5']) if pd.notna(row['ma5']) else None,
                    'ma10': float(row['ma10']) if pd.notna(row['ma10']) else None,
                    'ma20': float(row['ma20']) if pd.notna(row['ma20']) else None,
                    'ma60': float(row['ma60']) if pd.notna(row['ma60']) else None,
                    'rsi': float(row['rsi']) if pd.notna(row['rsi']) else None,
                    'macd': float(row['macd']) if pd.notna(row['macd']) else None,
                    'macd_signal': float(row['macd_signal']) if pd.notna(row['macd_signal']) else None,
                    'macd_hist': float(row['macd_hist']) if pd.notna(row['macd_hist']) else None,
                    'k': float(row['k']) if pd.notna(row['k']) else None,
                    'd': float(row['d']) if pd.notna(row['d']) else None,
                    'bb_upper': float(row['bb_upper']) if pd.notna(row['bb_upper']) else None,
                    'bb_middle': float(row['bb_middle']) if pd.notna(row['bb_middle']) else None,
                    'bb_lower': float(row['bb_lower']) if pd.notna(row['bb_lower']) else None,
                    'volume_ma5': float(row['volume_ma5']) if pd.notna(row['volume_ma5']) else None,
                    'volume_ma10': float(row['volume_ma10']) if pd.notna(row['volume_ma10']) else None,
                    'volume_ma20': float(row['volume_ma20']) if pd.notna(row['volume_ma20']) else None,
                    'updated_at': datetime.now()
                }
                
                bulk_operations.append(
                    UpdateOne(
                        {'symbol': symbol, 'date': row['date']},
                        {'$set': doc},
                        upsert=True
                    )
                )
            
            # 執行批次更新
            if bulk_operations:
                result = self.db.technical_indicators.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ {symbol}: 更新 {result.modified_count} 筆, 新增 {result.upserted_count} 筆")
                return result.modified_count + result.upserted_count
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ {symbol}: 處理失敗 - {e}")
            return 0
    
    def process_all(self, symbols=None, from_date=None):
        """處理多個股票"""
        # 如果沒有指定股票,取得所有有股價資料的股票
        if not symbols:
            pipeline = [
                {'$group': {'_id': '$symbol'}},
                {'$sort': {'_id': 1}}
            ]
            symbols = [doc['_id'] for doc in self.db.stock_price.aggregate(pipeline)]
        
        logger.info(f"📊 共需處理 {len(symbols)} 支股票")
        
        total_updated = 0
        success_count = 0
        failed_count = 0
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"\n[{i}/{len(symbols)}] 處理 {symbol}...")
            count = self.process_symbol(symbol, from_date)
            
            if count > 0:
                total_updated += count
                success_count += 1
            else:
                failed_count += 1
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 處理完成")
        logger.info("=" * 80)
        logger.info(f"✅ 成功: {success_count} 支")
        logger.info(f"❌ 失敗: {failed_count} 支")
        logger.info(f"📈 總更新: {total_updated:,} 筆")
        logger.info("=" * 80)
    
    def close(self):
        """關閉連線"""
        self.client.close()


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description='計算技術指標',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--symbols',
        type=str,
        help='股票代碼 (多個用逗號分隔, 例如: 2330,2317,2454)'
    )
    
    parser.add_argument(
        '--from-date',
        type=str,
        help='起始日期 (YYYY-MM-DD), 只更新此日期之後的資料'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='處理所有股票'
    )
    
    args = parser.parse_args()
    
    # 解析股票代碼
    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    elif not args.all:
        # 如果沒有指定 --all 且沒有指定股票,顯示幫助
        parser.print_help()
        sys.exit(1)
    
    logger.info("=" * 80)
    logger.info("📊 技術指標計算系統")
    logger.info("=" * 80)
    logger.info(f"⏰ 開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if symbols:
        logger.info(f"📋 股票代碼: {', '.join(symbols)}")
    else:
        logger.info("📋 處理範圍: 所有股票")
    
    if args.from_date:
        logger.info(f"📅 起始日期: {args.from_date}")
    
    logger.info("=" * 80)
    
    # 執行計算
    calculator = TechnicalIndicatorCalculator()
    
    try:
        calculator.process_all(symbols, args.from_date)
    finally:
        calculator.close()
    
    logger.info(f"\n⏰ 完成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
