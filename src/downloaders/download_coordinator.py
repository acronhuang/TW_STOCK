"""
下載協調器
統一管理所有資料表的下載流程
"""

import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pymongo import MongoClient
from .finmind_client import FinMindClient
from .table_config import get_all_tables, get_tables_by_category
from .data_validator import DataValidator


class DownloadCoordinator:
    """下載協調器"""
    
    def __init__(
        self,
        api_token: str,
        mongo_uri: str = "mongodb://localhost:27017/",
        db_name: str = "tw_stock_analysis",
        logger: Optional[logging.Logger] = None
    ):
        """
        初始化下載協調器
        
        Args:
            api_token: FinMind API Token
            mongo_uri: MongoDB 連線 URI
            db_name: 資料庫名稱
            logger: 日誌記錄器
        """
        self.api_client = FinMindClient(api_token, logger)
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client[db_name]
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化資料驗證器
        self.validator = DataValidator(logger)
        
        # 下載統計
        self.stats = {
            'total_tables': 0,
            'completed_tables': 0,
            'failed_tables': 0,
            'total_records': 0,
            'new_records': 0,
            'updated_records': 0,
            'skipped_records': 0,
            'validation_errors': 0,
            'start_time': None,
            'end_time': None
        }
        
    def download_all(self, categories: Optional[List[str]] = None, skip_existing: bool = True):
        """
        下載所有資料表
        
        Args:
            categories: 要下載的類別列表，None 表示全部
            skip_existing: 是否跳過已存在的資料
            
        Returns:
            下載結果統計
        """
        self.stats['start_time'] = datetime.now()
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 啟動全自動資料下載系統")
        self.logger.info("="*80)
        self.logger.info(f"📅 時間: {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"🔧 模式: {'跳過已存在資料' if skip_existing else '覆蓋下載'}")
        self.logger.info("="*80 + "\n")
        
        # 獲取要下載的資料表
        all_tables = get_all_tables()
        
        if categories:
            all_tables = [t for t in all_tables if t['category'] in categories]
            self.logger.info(f"📊 指定類別: {', '.join(categories)}")
        
        self.stats['total_tables'] = len(all_tables)
        self.logger.info(f"📊 總資料表數: {self.stats['total_tables']}\n")
        
        results = []
        
        for idx, table_config in enumerate(all_tables, 1):
            self.logger.info(f"\n{'#'*80}")
            self.logger.info(f"# [{idx}/{self.stats['total_tables']}] {table_config['category']} - {table_config['name']}")
            self.logger.info(f"# API 使用: {self.api_client.get_api_usage()['usage_percent']}%")
            self.logger.info(f"{'#'*80}\n")
            
            # 檢查是否已停用（FinMind API 已移除）
            if table_config.get('disabled', False):
                reason = table_config.get('disabled_reason', 'API 不可用')
                self.logger.warning(f"⏭️  跳過：{reason}")
                self.stats['completed_tables'] += 1  # 計入完成（避免視為失敗）
                results.append({
                    'name': table_config['name'],
                    'status': 'skipped',
                    'reason': reason,
                    'total_records': 0,
                    'new_records': 0
                })
                continue
            
            # 檢查 API 配額
            if self.api_client.api_call_count >= self.api_client.api_quota_per_hour - 10:
                self.logger.warning("⚠️  API 配額不足，停止下載")
                break
            
            try:
                result = self.download_table(table_config, skip_existing)
                results.append(result)
                
                if result['status'] == 'success':
                    self.stats['completed_tables'] += 1
                else:
                    self.stats['failed_tables'] += 1
                
                self.stats['total_records'] += result.get('total_records', 0)
                self.stats['new_records'] += result.get('new_records', 0)
                self.stats['updated_records'] += result.get('updated_records', 0)
                self.stats['skipped_records'] += result.get('skipped_records', 0)
                
            except Exception as e:
                self.logger.error(f"❌ 處理失敗: {e}")
                self.stats['failed_tables'] += 1
                results.append({
                    'name': table_config['name'],
                    'status': 'error',
                    'error': str(e)
                })
            
            # 每 10 個任務休息一下
            if idx % 10 == 0 and idx < self.stats['total_tables']:
                self.logger.info("\n⏸️  休息 3 秒...")
                time.sleep(3)
        
        self.stats['end_time'] = datetime.now()
        self._print_summary(results)
        
        return {
            'stats': self.stats,
            'results': results,
            'api_usage': self.api_client.get_api_usage()
        }
    
    def download_table(self, table_config: Dict, skip_existing: bool = True) -> Dict:
        """
        下載單一資料表
        
        Args:
            table_config: 資料表配置
            skip_existing: 是否跳過已存在的資料
            
        Returns:
            下載結果
        """
        name = table_config['name']
        dataset = table_config['dataset']
        collection_name = table_config['collection']
        params = table_config.get('params', {}).copy()
        indexes = table_config.get('indexes', [])
        unique_keys = table_config.get('unique_keys', [])
        needs_symbols = table_config.get('needs_symbols', False)
        batch_size = table_config.get('batch_size', 100)
        
        self.logger.info(f"📥 下載: {name}")
        self.logger.info(f"   Dataset: {dataset}")
        self.logger.info(f"   Collection: {collection_name}")
        
        collection = self.db[collection_name]
        
        result = {
            'name': name,
            'dataset': dataset,
            'collection': collection_name,
            'status': 'success',
            'total_records': 0,
            'new_records': 0,
            'updated_records': 0,
            'skipped_records': 0,
            'validation_errors': 0
        }
        
        try:
            if needs_symbols:
                # 需要逐股票下載
                symbols = self._get_symbols()
                total_symbols = min(batch_size, len(symbols))
                self.logger.info(f"   處理股票數: {total_symbols}")
                
                for i, symbol in enumerate(symbols[:batch_size], 1):
                    # 檢查是否已有資料
                    if skip_existing and self._has_recent_data(collection, symbol):
                        self.logger.debug(f"   [{i}/{total_symbols}] {symbol}... ⏭️  跳過")
                        result['skipped_records'] += 1
                        continue
                    
                    symbol_params = {**params, "stock_id": symbol}
                    data = self.api_client.fetch_data(dataset, symbol_params)
                    
                    if data:
                        # 儲存資料（含驗證）
                        saved = self._save_data(collection, data, unique_keys, symbol, dataset)
                        result['total_records'] += len(data)
                        result['new_records'] += saved['inserted']
                        result['updated_records'] += saved['updated']
                        result['validation_errors'] += saved.get('validation_errors', 0)
                        
                        self.logger.info(f"   [{i}/{total_symbols}] {symbol}... ✅ {len(data)} 筆")
                    else:
                        self.logger.debug(f"   [{i}/{total_symbols}] {symbol}... ⚠️  無資料")
                    
                    time.sleep(0.05)  # 避免請求過快
                    
            else:
                # 整體下載（不需要股票代碼）
                # 檢查是否已有最新資料
                if skip_existing and self._has_recent_data(collection):
                    self.logger.info(f"   ⏭️  資料已是最新，跳過下載")
                    result['status'] = 'skipped'
                    return result
                
                data = self.api_client.fetch_data(dataset, params)
                
                if data:
                    saved = self._save_data(collection, data, unique_keys, None, dataset)
                    result['total_records'] = len(data)
                    result['new_records'] = saved['inserted']
                    result['updated_records'] = saved['updated']
                    result['validation_errors'] = saved.get('validation_errors', 0)
                    
                    self.logger.info(f"   ✅ {len(data)} 筆 (新增 {saved['inserted']}, 更新 {saved['updated']})")
                else:
                    self.logger.warning(f"   ⚠️  無資料")
                    result['status'] = 'no_data'
            
            # 建立索引
            if indexes and result['total_records'] > 0:
                self._create_indexes(collection_name, indexes)
            
        except Exception as e:
            self.logger.error(f"   ❌ 錯誤: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    def _get_symbols(self) -> List[str]:
        """從資料庫獲取股票代碼（過濾 ETF）"""
        try:
            # 嘗試從 taiwan_stock_info 獲取
            symbols = list(self.db.taiwan_stock_info.distinct('stock_id'))
            if symbols:
                return self._filter_etf(symbols)
            
            # 備用：從 tickers 獲取
            symbols = list(self.db.tickers.distinct('symbol'))
            if symbols:
                return self._filter_etf(symbols)
            
            # 再備用：從 stocks 獲取
            symbols = list(self.db.stocks.distinct('symbol'))
            return self._filter_etf(symbols)
            
        except Exception as e:
            self.logger.warning(f"獲取股票代碼失敗: {e}")
            return []
    
    def _filter_etf(self, symbols: List[str]) -> List[str]:
        """
        過濾 ETF、權證及其他特殊代碼
        
        過濾規則：
        1. ETF (00開頭的 4 位數，如 0050, 0051, 0056)
        2. ETF (00開頭的 6 位數，如 006208)
        3. ETF (00開頭 + 字母後綴，如 00633L, 00634R, 00635U)
        4. 權證 (5位數 + T，如 01004T)
        5. 特殊代碼 (02開頭的 6 位數，如 020000)
        6. 其他衍生品 (5位數 + 其他字母，如 02001B)
        
        Args:
            symbols: 原始股票列表
            
        Returns:
            過濾後的股票列表（僅包含正常股票）
        """
        filtered = []
        filter_stats = {
            'etf_4digit': 0,      # 4位數 ETF (00xx)
            'etf_6digit': 0,      # 6位數 ETF
            'etf_letter': 0,      # 字母後綴 ETF
            'warrant': 0,         # 權證
            'special_6digit': 0,  # 特殊 6位數
            'other_derivative': 0 # 其他衍生品
        }
        
        for symbol in symbols:
            if not symbol:
                continue
            
            should_filter = False
            filter_reason = ""
            
            # 規則 1: ETF（00開頭的 4 位數，如 0050, 0051, 0056）
            if symbol.startswith('00') and len(symbol) == 4 and symbol.isdigit():
                should_filter = True
                filter_stats['etf_4digit'] += 1
                filter_reason = "ETF(4位數)"
            
            # 規則 2 & 3: ETF（00開頭且至少 5 位數）
            elif symbol.startswith('00') and len(symbol) >= 5:
                # 檢查前 5 碼是否為數字（006XX 格式）
                if symbol[:5].isdigit():
                    should_filter = True
                    filter_stats['etf_6digit'] += 1
                    filter_reason = "ETF(6位數)"
                # 檢查前 4 碼數字 + 字母（00XXL/R/U 格式）
                elif len(symbol) >= 5 and symbol[:4].isdigit() and symbol[4].isalpha():
                    should_filter = True
                    filter_stats['etf_letter'] += 1
                    filter_reason = "ETF(字母)"
            
            # 規則 3: 權證（5位數 + T）
            elif len(symbol) == 6 and symbol[:5].isdigit() and symbol.endswith('T'):
                should_filter = True
                filter_stats['warrant'] += 1
                filter_reason = "權證"
            
            # 規則 4: 特殊代碼（02開頭的 6 位數）
            elif len(symbol) == 6 and symbol.startswith('02') and symbol.isdigit():
                should_filter = True
                filter_stats['special_6digit'] += 1
                filter_reason = "特殊代碼"
            
            # 規則 5: 其他衍生品（5位數 + 其他字母，非T）
            elif len(symbol) == 6 and symbol[:5].isdigit() and symbol[5].isalpha():
                should_filter = True
                filter_stats['other_derivative'] += 1
                filter_reason = "衍生品"
            
            if should_filter:
                self.logger.debug(f"   跳過 {filter_reason}: {symbol}")
            else:
                filtered.append(symbol)
        
        # 統計輸出
        total_filtered = sum(filter_stats.values())
        if total_filtered > 0:
            etf_total = filter_stats['etf_4digit'] + filter_stats['etf_6digit'] + filter_stats['etf_letter']
            other_total = filter_stats['special_6digit'] + filter_stats['other_derivative']
            self.logger.info(f"   已過濾 {total_filtered} 個特殊代碼 "
                           f"(ETF: {etf_total}, "
                           f"權證: {filter_stats['warrant']}, "
                           f"其他: {other_total})")
        
        return filtered
    
    def _has_recent_data(self, collection, symbol: Optional[str] = None) -> bool:
        """
        檢查是否有最新資料
        
        Args:
            collection: MongoDB collection
            symbol: 股票代碼（可選）
            
        Returns:
            是否有最新資料
        """
        try:
            query = {}
            if symbol:
                query['stock_id'] = symbol
            
            # 檢查是否有今天或昨天的資料
            today = datetime.now().strftime("%Y-%m-%d")
            latest = collection.find_one(query, sort=[('date', -1)])
            
            if latest and 'date' in latest:
                latest_date = latest['date']
                # 如果最新資料是今天或昨天，認為是最新的
                return latest_date >= datetime.now().strftime("%Y-%m-%d")
            
            return False
            
        except Exception:
            return False
    
    def _save_data(self, collection, data: List[Dict], unique_keys: List[str], symbol: Optional[str] = None, dataset: Optional[str] = None) -> Dict:
        """
        儲存資料到 MongoDB（含資料驗證）
        
        Args:
            collection: MongoDB collection
            data: 資料列表
            unique_keys: 唯一鍵欄位
            symbol: 股票代碼（可選）
            dataset: 資料集名稱（用於判斷驗證類型）
            
        Returns:
            儲存統計
        """
        inserted = 0
        updated = 0
        validation_errors = 0
        
        for record in data:
            # 確保有 symbol 欄位
            if symbol and 'symbol' not in record:
                record['symbol'] = symbol
            if symbol and 'stock_id' not in record:
                record['stock_id'] = symbol
            
            # 資料驗證（僅針對價格資料）
            if dataset and 'Price' in dataset:
                is_valid, error_msg = self.validator.validate_price_data(record)
                if not is_valid:
                    validation_errors += 1
                    self.validator.log_error(f"[{dataset}] {error_msg}")
                    # 跳過不合法的資料
                    continue
            
            # 驗證財報資料
            if dataset and ('FinancialStatement' in dataset or 'BalanceSheet' in dataset):
                is_valid, error_msg = self.validator.validate_financial_data(record)
                if not is_valid:
                    validation_errors += 1
                    self.validator.log_error(f"[{dataset}] {error_msg}")
                    # 仍然儲存，但記錄警告
                    self.logger.warning(f"   ⚠️  財報資料異常但仍儲存: {error_msg}")
            
            # 驗證股利資料
            if dataset and 'Dividend' in dataset:
                is_valid, error_msg = self.validator.validate_dividend_data(record)
                if not is_valid:
                    validation_errors += 1
                    self.validator.log_error(f"[{dataset}] {error_msg}")
            
            # 建立查詢條件
            query = {}
            for key in unique_keys:
                if key in record:
                    query[key] = record[key]
            
            if not query:
                # 如果沒有唯一鍵，使用所有欄位
                query = record
            
            # 加入更新時間
            record['updated_at'] = datetime.now()
            
            # Upsert
            result = collection.update_one(query, {'$set': record}, upsert=True)
            
            if result.upserted_id:
                inserted += 1
            elif result.modified_count > 0:
                updated += 1
        
        return {
            'inserted': inserted,
            'updated': updated,
            'validation_errors': validation_errors
        }
    
    def _create_indexes(self, collection_name: str, indexes: List):
        """建立索引"""
        try:
            collection = self.db[collection_name]
            for index in indexes:
                collection.create_index([index], background=True)
            self.logger.debug(f"   ✅ 索引建立完成")
        except Exception as e:
            self.logger.warning(f"   索引建立警告: {e}")
    
    def _print_summary(self, results: List[Dict]):
        """列印摘要報告"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 下載完成報告")
        self.logger.info("="*80)
        self.logger.info(f"⏱️  總耗時: {duration:.0f} 秒 ({duration/60:.1f} 分鐘)")
        self.logger.info(f"📋 完成任務: {self.stats['completed_tables']}/{self.stats['total_tables']}")
        self.logger.info(f"❌ 失敗任務: {self.stats['failed_tables']}")
        self.logger.info(f"📊 總記錄數: {self.stats['total_records']:,}")
        self.logger.info(f"   ├─ 新增: {self.stats['new_records']:,}")
        self.logger.info(f"   ├─ 更新: {self.stats['updated_records']:,}")
        self.logger.info(f"   └─ 跳過: {self.stats['skipped_records']:,}")
        
        # API 使用統計
        api_usage = self.api_client.get_api_usage()
        self.logger.info(f"\n🔌 API 使用:")
        self.logger.info(f"   └─ {api_usage['call_count']}/{api_usage['quota']} ({api_usage['usage_percent']}%)")
        
        # 各類別統計
        self.logger.info("\n📊 各類別統計:")
        for category in ['技術面', '籌碼面', '基本面', '衍生性金融商品', '其他']:
            category_results = [r for r in results if r.get('name') in [
                t['name'] for t in get_tables_by_category(category)
            ]]
            if category_results:
                success = len([r for r in category_results if r.get('status') == 'success'])
                total_records = sum(r.get('total_records', 0) for r in category_results)
                self.logger.info(f"   {category}: {success}/{len(category_results)} ({total_records:,} 筆)")
        
        self.logger.info("\n" + "="*80)
        self.logger.info("✅ 下載系統執行完畢")
        self.logger.info("="*80 + "\n")
    
    def close(self):
        """關閉連線"""
        self.mongo_client.close()
        self.logger.info("MongoDB 連線已關閉")
