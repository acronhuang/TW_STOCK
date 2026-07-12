#!/usr/bin/env python3
"""
背景完整資料下載器
- 不跳過已有資料，確保所有股票都有完整歷史資料
- API 限制管理（每小時 600 次）
- 狀態查詢機制
- 進度記錄與斷點續傳
"""

import requests
from pymongo import MongoClient
from datetime import datetime, timedelta
import logging
import time
import json
import os
from pathlib import Path

# FinMind API Token
FINMIND_TOKEN = ""

# 配置
MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME = 'tw_stock_analysis'
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
START_DATE = '2016-02-16'  # 10年前
END_DATE = datetime.now().strftime('%Y-%m-%d')
HOUR_LIMIT = 600  # 每小時限制

# 狀態檔案
STATUS_FILE = Path(__file__).parent.parent / 'download_status.json'
LOG_FILE = Path(__file__).parent.parent / 'logs' / f'full_download_{datetime.now().strftime("%Y%m%d")}.log'

# 確保 logs 目錄存在
LOG_FILE.parent.mkdir(exist_ok=True)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BackgroundDownloader:
    """背景完整資料下載器"""
    
    def __init__(self):
        self.client = MongoClient(MONGO_URI)
        self.db = self.client[DB_NAME]
        
        # 載入或初始化狀態
        self.status = self._load_status()
        
        # 統計
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'api_calls_this_hour': 0,
            'hour_start_time': datetime.now(),
            'stocks_processed': 0,
            'stocks_success': 0,
            'stocks_failed': 0,
            'prices_downloaded': 0,
            'institutional_downloaded': 0,
            'errors': []
        }
    
    def _load_status(self):
        """載入進度狀態"""
        if STATUS_FILE.exists():
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        return {
            'last_symbol': None,
            'processed_symbols': [],
            'failed_symbols': [],
            'total_processed': 0,
            'last_update': None
        }
    
    def _save_status(self):
        """儲存進度狀態"""
        self.status['last_update'] = datetime.now().isoformat()
        with open(STATUS_FILE, 'w') as f:
            json.dump(self.status, f, indent=2)
    
    def _check_api_limit(self):
        """檢查並管理 API 限制"""
        # 檢查是否過了一小時
        elapsed = (datetime.now() - self.stats['hour_start_time']).total_seconds()
        if elapsed >= 3600:
            logger.info(f"✅ 小時重置 - 已用 {self.stats['api_calls_this_hour']} 次")
            self.stats['api_calls_this_hour'] = 0
            self.stats['hour_start_time'] = datetime.now()
        
        # 如果接近限制，等待
        if self.stats['api_calls_this_hour'] >= HOUR_LIMIT - 10:
            wait_time = 3600 - elapsed
            logger.warning(f"⚠️  接近 API 限制 ({self.stats['api_calls_this_hour']}/{HOUR_LIMIT})")
            logger.warning(f"⏰ 等待 {wait_time/60:.1f} 分鐘後繼續...")
            time.sleep(wait_time + 60)
            self.stats['api_calls_this_hour'] = 0
            self.stats['hour_start_time'] = datetime.now()
    
    def get_stock_list(self):
        """獲取股票清單"""
        stocks = list(self.db.stocks.find({}, {'symbol': 1, '_id': 0}))
        symbols = [s['symbol'] for s in stocks]
        
        # 移除已處理成功的
        remaining = [s for s in symbols if s not in self.status['processed_symbols']]
        
        logger.info(f"📋 總股票: {len(symbols)} 檔")
        logger.info(f"✅ 已完成: {len(self.status['processed_symbols'])} 檔")
        logger.info(f"🔄 待處理: {len(remaining)} 檔")
        
        return remaining
    
    def download_prices(self, symbol: str) -> tuple:
        """下載股價資料 - 不檢查已有資料，直接下載更新"""
        try:
            self._check_api_limit()
            
            params = {
                'dataset': 'TaiwanStockPrice',
                'data_id': symbol,
                'start_date': START_DATE,
                'end_date': END_DATE,
                'token': FINMIND_TOKEN
            }
            
            logger.info(f"[{symbol}] 📥 下載股價資料...")
            response = requests.get(FINMIND_API, params=params, timeout=30)
            self.stats['api_calls_this_hour'] += 1
            
            if response.status_code != 200:
                logger.error(f"[{symbol}] API 錯誤: {response.status_code}")
                return False, 0
            
            data = response.json()
            
            if data.get('status') != 200 or not data.get('data'):
                logger.warning(f"[{symbol}] 無股價資料")
                return True, 0  # 成功但無資料
            
            # 處理並存入 - 使用 upsert 更新或插入
            count = 0
            for item in data['data']:
                record = {
                    'symbol': symbol,
                    'date': item['date'],
                    'open': float(item['open']),
                    'high': float(item['max']),
                    'low': float(item['min']),
                    'close': float(item['close']),
                    'volume': int(item['Trading_Volume']),
                    'turnover': float(item.get('Trading_turnover', 0)),
                    'updated_at': datetime.now()
                }
                
                self.db.stock_price.update_one(
                    {'symbol': symbol, 'date': record['date']},
                    {'$set': record},
                    upsert=True
                )
                count += 1
            
            self.stats['prices_downloaded'] += count
            logger.info(f"[{symbol}] ✅ 股價 {count} 筆")
            return True, count
            
        except Exception as e:
            logger.error(f"[{symbol}] 股價錯誤: {e}")
            self.stats['errors'].append({
                'symbol': symbol,
                'type': 'price',
                'error': str(e),
                'time': datetime.now().isoformat()
            })
            return False, 0
    
    def download_institutional(self, symbol: str) -> tuple:
        """下載三大法人資料"""
        try:
            self._check_api_limit()
            
            params = {
                'dataset': 'TaiwanStockInstitutionalInvestors',
                'data_id': symbol,
                'start_date': START_DATE,
                'end_date': END_DATE,
                'token': FINMIND_TOKEN
            }
            
            logger.info(f"[{symbol}] 📥 下載三大法人...")
            response = requests.get(FINMIND_API, params=params, timeout=30)
            self.stats['api_calls_this_hour'] += 1
            
            if response.status_code != 200:
                logger.error(f"[{symbol}] 三大法人 API 錯誤")
                return False, 0
            
            data = response.json()
            
            if data.get('status') != 200 or not data.get('data'):
                return True, 0  # 成功但無資料
            
            count = 0
            for item in data['data']:
                record = {
                    'symbol': symbol,
                    'date': item['date'],
                    'foreign_buy': int(item.get('buy', 0)),
                    'foreign_sell': int(item.get('sell', 0)),
                    'foreign_net': int(item.get('buy', 0)) - int(item.get('sell', 0)),
                    'investment_trust_net': 0,
                    'dealer_net': 0,
                    'updated_at': datetime.now()
                }
                
                self.db.institutional_investors.update_one(
                    {'symbol': symbol, 'date': record['date']},
                    {'$set': record},
                    upsert=True
                )
                count += 1
            
            self.stats['institutional_downloaded'] += count
            logger.info(f"[{symbol}] ✅ 三大法人 {count} 筆")
            return True, count
            
        except Exception as e:
            logger.error(f"[{symbol}] 三大法人錯誤: {e}")
            self.stats['errors'].append({
                'symbol': symbol,
                'type': 'institutional',
                'error': str(e),
                'time': datetime.now().isoformat()
            })
            return False, 0
    
    def run(self):
        """執行完整下載"""
        logger.info("=" * 80)
        logger.info("🚀 背景完整資料下載器啟動")
        logger.info("=" * 80)
        logger.info(f"📊 API Token: 已設定")
        logger.info(f"⏰ 時間範圍: {START_DATE} 至 {END_DATE}")
        logger.info(f"🔧 API 限制: 每小時 {HOUR_LIMIT} 次")
        logger.info(f"📝 狀態檔案: {STATUS_FILE}")
        logger.info(f"📋 日誌檔案: {LOG_FILE}")
        logger.info("=" * 80)
        
        symbols = self.get_stock_list()
        total = len(symbols)
        
        if total == 0:
            logger.info("✅ 所有股票已處理完成！")
            return
        
        start_time = time.time()
        
        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info("")
                logger.info(f"{'='*60}")
                logger.info(f"[{i}/{total}] {symbol}")
                logger.info(f"{'='*60}")
                
                # 下載股價
                price_success, price_count = self.download_prices(symbol)
                time.sleep(0.5)
                
                # 下載三大法人
                inst_success, inst_count = self.download_institutional(symbol)
                time.sleep(0.5)
                
                # 更新統計
                self.stats['stocks_processed'] += 1
                
                if price_success and inst_success:
                    self.stats['stocks_success'] += 1
                    self.status['processed_symbols'].append(symbol)
                else:
                    self.stats['stocks_failed'] += 1
                    self.status['failed_symbols'].append(symbol)
                
                self.status['last_symbol'] = symbol
                self.status['total_processed'] = len(self.status['processed_symbols'])
                
                # 每 5 檔儲存狀態
                if i % 5 == 0:
                    self._save_status()
                
                # 每 10 檔顯示進度
                if i % 10 == 0:
                    elapsed = time.time() - start_time
                    avg_time = elapsed / i
                    remaining_time = (total - i) * avg_time
                    
                    logger.info("")
                    logger.info("=" * 80)
                    logger.info(f"📊 進度報告")
                    logger.info("=" * 80)
                    logger.info(f"  進度:          {i}/{total} ({i/total*100:.1f}%)")
                    logger.info(f"  已用時間:      {elapsed/60:.1f} 分鐘")
                    logger.info(f"  預估剩餘:      {remaining_time/60:.1f} 分鐘")
                    logger.info(f"  股票成功:      {self.stats['stocks_success']}")
                    logger.info(f"  股票失敗:      {self.stats['stocks_failed']}")
                    logger.info(f"  股價記錄:      {self.stats['prices_downloaded']:,}")
                    logger.info(f"  三大法人:      {self.stats['institutional_downloaded']:,}")
                    logger.info(f"  API 呼叫:      {self.stats['api_calls_this_hour']}/{HOUR_LIMIT}")
                    logger.info(f"  錯誤數:        {len(self.stats['errors'])}")
                    logger.info("=" * 80)
                
            except Exception as e:
                logger.error(f"[{symbol}] 處理錯誤: {e}")
                self.stats['stocks_failed'] += 1
                self.status['failed_symbols'].append(symbol)
                continue
        
        # 完成
        self._save_status()
        total_time = time.time() - start_time
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ 完整下載完成！")
        logger.info("=" * 80)
        logger.info(f"  總處理:        {self.stats['stocks_processed']}/{total}")
        logger.info(f"  成功:          {self.stats['stocks_success']}")
        logger.info(f"  失敗:          {self.stats['stocks_failed']}")
        logger.info(f"  股價記錄:      {self.stats['prices_downloaded']:,}")
        logger.info(f"  三大法人:      {self.stats['institutional_downloaded']:,}")
        logger.info(f"  總 API 呼叫:   {self.stats['api_calls_this_hour']}")
        logger.info(f"  總耗時:        {total_time/60:.1f} 分鐘")
        logger.info(f"  平均速度:      {total_time/total:.1f} 秒/股")
        logger.info("=" * 80)
        
        if self.stats['errors']:
            logger.info(f"⚠️  錯誤數量: {len(self.stats['errors'])}")
            logger.info(f"  詳細錯誤請查看: {LOG_FILE}")


def show_status():
    """顯示當前下載狀態"""
    if not STATUS_FILE.exists():
        print("❌ 尚未開始下載")
        return
    
    with open(STATUS_FILE, 'r') as f:
        status = json.load(f)
    
    print("=" * 80)
    print("📊 下載狀態")
    print("=" * 80)
    print(f"  最後處理:      {status.get('last_symbol', 'N/A')}")
    print(f"  已完成:        {len(status.get('processed_symbols', []))} 檔")
    print(f"  失敗:          {len(status.get('failed_symbols', []))} 檔")
    print(f"  總進度:        {status.get('total_processed', 0)} 檔")
    print(f"  最後更新:      {status.get('last_update', 'N/A')}")
    print("=" * 80)
    
    if status.get('failed_symbols'):
        print(f"\n❌ 失敗股票: {', '.join(status['failed_symbols'][:10])}")
        if len(status['failed_symbols']) > 10:
            print(f"   ... 及其他 {len(status['failed_symbols'])-10} 檔")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='背景完整資料下載器')
    parser.add_argument('--status', action='store_true', help='顯示下載狀態')
    parser.add_argument('--reset', action='store_true', help='重置下載進度')
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.reset:
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()
            print("✅ 下載進度已重置")
        else:
            print("❌ 無進度檔案")
    else:
        downloader = BackgroundDownloader()
        downloader.run()
