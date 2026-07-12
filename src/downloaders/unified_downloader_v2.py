#!/usr/bin/env python3
"""
帶續傳功能的統一下載程式 v2
- 斷點續傳
- 智能跳過 ETF
- API 配額管理
- 自動等待重試（可選）

使用範例:
    # 下載基本面數據（支持續傳）
    python3 unified_downloader_v2.py --categories 基本面
    
    # 重置進度重新開始
    python3 unified_downloader_v2.py --categories 基本面 --reset
    
    # 自動等待配額重置後繼續
    python3 unified_downloader_v2.py --categories 基本面 --auto-retry
"""

import os
import sys
import argparse
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# 設定環境變數和路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.downloaders.download_coordinator import DownloadCoordinator
from src.downloaders.table_config import get_all_tables
from src.downloaders.progress_manager import ProgressManager


def setup_logging(verbose: bool = False) -> logging.Logger:
    """設定日誌系統"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"smart_download_{timestamp}.log"
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"📝 日誌檔案: {log_file}")
    return logger


class SmartDownloadCoordinator(DownloadCoordinator):
    """帶進度管理的智能下載協調器"""
    
    def __init__(self, *args, progress_manager: ProgressManager, **kwargs):
        super().__init__(*args, **kwargs)
        self.progress = progress_manager
    
    def download_all_with_resume(
        self,
        categories: Optional[List[str]] = None,
        skip_existing: bool = True
    ):
        """
        支持續傳的下載功能
        
        Args:
            categories: 要下載的類別列表
            skip_existing: 是否跳過已存在的資料
        """
        self.stats['start_time'] = datetime.now()
        
        # 檢查是否有未完成的進度
        resume_info = self.progress.get_resume_info()
        if resume_info["can_resume"]:
            self.logger.info("\n" + "="*80)
            self.logger.info("🔄 發現未完成的下載，將從中斷點繼續")
            self.progress.print_summary()
        
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 智能下載系統 v2（帶續傳功能）")
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
            table_name = table_config['name']
            
            # 跳過已完成的表
            if self.progress.is_table_completed(table_name):
                self.logger.info(f"\n[{idx}/{self.stats['total_tables']}] {table_name} - ✅ 已完成，跳過")
                self.stats['completed_tables'] += 1
                continue
            
            self.logger.info(f"\n{'#'*80}")
            self.logger.info(f"# [{idx}/{self.stats['total_tables']}] {table_config['category']} - {table_name}")
            self.logger.info(f"# API 使用: {self.api_client.get_api_usage()['usage_percent']}%")
            self.logger.info(f"{'#'*80}\n")
            
            # 檢查 API 配額
            api_usage = self.api_client.get_api_usage()
            if api_usage['call_count'] >= api_usage['quota'] - 10:
                self.logger.warning("⚠️  API 配額不足，保存進度並停止")
                self.progress.update_api_usage(
                    api_usage['call_count'],
                    api_usage['quota']
                )
                self.progress.save_progress()
                break
            
            # 設定當前表
            self.progress.set_current_table(table_name)
            
            try:
                # 下載資料表（帶續傳）
                result = self.download_table_with_resume(table_config, skip_existing)
                results.append(result)
                
                if result['status'] == 'success':
                    self.stats['completed_tables'] += 1
                    self.progress.mark_table_completed(table_name)
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
                    'name': table_name,
                    'status': 'error',
                    'error': str(e)
                })
            
            # 定期保存進度
            self.progress.save_progress()
            
            # 每 5 個任務休息一下
            if idx % 5 == 0 and idx < self.stats['total_tables']:
                self.logger.info("\n⏸️  休息 3 秒...")
                time.sleep(3)
        
        self.stats['end_time'] = datetime.now()
        self._print_summary(results)
        
        return {
            'stats': self.stats,
            'results': results,
            'api_usage': self.api_client.get_api_usage()
        }
    
    def download_table_with_resume(self, table_config: dict, skip_existing: bool = True):
        """
        帶續傳功能的資料表下載
        
        Args:
            table_config: 資料表配置
            skip_existing: 是否跳過已存在的資料
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
                total_symbols = len(symbols)
                
                # 計算進度
                processed_count = self.progress.get_processed_count(name)
                self.logger.info(f"   總股票數: {total_symbols}")
                self.logger.info(f"   已處理: {processed_count}")
                self.logger.info(f"   黑名單: {len(self.progress.progress['blacklist'])}")
                
                processed_in_this_run = 0
                
                for i, symbol in enumerate(symbols, 1):
                    # 跳過已處理的股票
                    if self.progress.is_stock_processed(name, symbol):
                        continue
                    
                    # 智能跳過（ETF、黑名單）
                    if self.progress.should_skip_stock(symbol):
                        self.logger.debug(f"   [{i}/{total_symbols}] {symbol}... 🚫 跳過（ETF/黑名單）")
                        self.progress.mark_stock_processed(name, symbol)
                        result['skipped_records'] += 1
                        continue
                    
                    # 檢查是否已有資料
                    if skip_existing and self._has_recent_data(collection, symbol):
                        self.logger.debug(f"   [{i}/{total_symbols}] {symbol}... ⏭️  已有資料")
                        self.progress.mark_stock_processed(name, symbol)
                        result['skipped_records'] += 1
                        continue
                    
                    # 下載數據
                    symbol_params = {**params, "stock_id": symbol}
                    data = self.api_client.fetch_data(dataset, symbol_params)
                    
                    if data:
                        # 儲存資料
                        saved = self._save_data(collection, data, unique_keys, symbol, dataset)
                        result['total_records'] += len(data)
                        result['new_records'] += saved['inserted']
                        result['updated_records'] += saved['updated']
                        result['validation_errors'] += saved.get('validation_errors', 0)
                        
                        self.logger.info(f"   [{i}/{total_symbols}] {symbol}... ✅ {len(data)} 筆")
                        self.progress.mark_stock_processed(name, symbol)
                    else:
                        self.logger.debug(f"   [{i}/{total_symbols}] {symbol}... ⚠️  無資料")
                        # 標記為無數據，下次跳過
                        self.progress.add_to_blacklist(symbol, "API 返回空數據")
                        self.progress.mark_stock_processed(name, symbol)
                    
                    processed_in_this_run += 1
                    
                    # 每 50 支股票保存一次進度
                    if processed_in_this_run % 50 == 0:
                        self.progress.save_progress()
                        self.logger.debug(f"   💾 進度已保存（處理 {processed_in_this_run} 支）")
                    
                    time.sleep(0.05)  # 避免請求過快
                    
            else:
                # 整體下載（不需要股票代碼）
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
                    
                    self.logger.info(f"   ✅ {len(data)} 筆（新增 {saved['inserted']}, 更新 {saved['updated']}）")
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


def wait_for_quota_reset(logger: logging.Logger):
    """等待 API 配額重置"""
    next_hour = datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    wait_seconds = (next_hour - datetime.now()).total_seconds()
    
    logger.info(f"\n⏰ API 配額已用完，等待至 {next_hour.strftime('%H:%M')} 重置")
    logger.info(f"   等待時間: {int(wait_seconds/60)} 分鐘")
    
    # 顯示倒數
    while datetime.now() < next_hour:
        remaining = (next_hour - datetime.now()).total_seconds()
        mins, secs = divmod(int(remaining), 60)
        print(f"\r   ⏳ 剩餘: {mins:02d}:{secs:02d}", end='', flush=True)
        time.sleep(1)
    
    print("\n✅ 配額已重置，繼續下載...\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="台股資料智能下載程式 v2 - 支持斷點續傳、智能跳過 ETF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  下載基本面（續傳）:        python unified_downloader_v2.py --categories 基本面
  重置進度重新開始:          python unified_downloader_v2.py --categories 基本面 --reset
  自動等待配額重置:          python unified_downloader_v2.py --categories 基本面 --auto-retry
  查看當前進度:              python unified_downloader_v2.py --show-progress
        """
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='下載所有資料表'
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        choices=['技術面', '基本面', '籌碼面', '衍生性商品'],
        help='指定下載類別'
    )
    
    parser.add_argument(
        '--reset',
        action='store_true',
        help='重置進度，從頭開始下載'
    )
    
    parser.add_argument(
        '--auto-retry',
        action='store_true',
        help='API 配額用完時自動等待 1 小時後繼續'
    )
    
    parser.add_argument(
        '--show-progress',
        action='store_true',
        help='顯示當前進度'
    )
    
    parser.add_argument(
        '--no-skip',
        action='store_true',
        help='不跳過已存在的資料'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細日誌輸出'
    )
    
    parser.add_argument(
        '--mongo-uri',
        default='mongodb://localhost:27017/',
        help='MongoDB 連線 URI'
    )
    
    parser.add_argument(
        '--db-name',
        default='tw_stock_analysis',
        help='資料庫名稱'
    )
    
    args = parser.parse_args()
    
    # 設定日誌
    logger = setup_logging(args.verbose)
    
    # 初始化進度管理器
    progress = ProgressManager(logger=logger)
    
    # 顯示進度
    if args.show_progress:
        progress.print_summary()
        return
    
    # 重置進度
    if args.reset:
        logger.info("🔄 重置下載進度...")
        progress.reset_progress(keep_blacklist=True)
        logger.info("✅ 進度已重置（保留黑名單）\n")
    
    # 驗證參數
    if not args.all and not args.categories:
        parser.error("請指定 --all 或 --categories")
    
    # 獲取 API Token
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 錯誤: 未設定 FINMIND_API_TOKEN 環境變數")
        print("\n請執行: export FINMIND_API_TOKEN='your_token_here'")
        sys.exit(1)
    
    # 啟動資訊
    print("\n" + "="*80)
    print("🚀 台股資料智能下載系統 v2")
    print("="*80)
    print(f"📅 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 模式: {'覆蓋下載' if args.no_skip else '跳過已存在資料'}")
    print(f"🔄 續傳: 啟用")
    print(f"⏰ 自動重試: {'啟用' if args.auto_retry else '停用'}")
    
    if args.all:
        print(f"📊 範圍: 全部資料表")
    else:
        print(f"📊 範圍: {', '.join(args.categories)}")
    
    print("="*80 + "\n")
    
    # 初始化下載協調器
    logger.info("初始化智能下載協調器...")
    coordinator = SmartDownloadCoordinator(
        api_token=api_token,
        mongo_uri=args.mongo_uri,
        db_name=args.db_name,
        logger=logger,
        progress_manager=progress
    )
    
    # 執行下載（支持自動重試）
    while True:
        try:
            skip_existing = not args.no_skip
            categories = None if args.all else args.categories
            
            logger.info("開始下載資料...")
            result = coordinator.download_all_with_resume(
                categories=categories,
                skip_existing=skip_existing
            )
            
            # 檢查是否因 API 配額停止
            api_usage = result['api_usage']
            if api_usage['call_count'] >= api_usage['quota'] - 10:
                logger.warning(f"\n⚠️  API 配額接近上限 ({api_usage['call_count']}/{api_usage['quota']})")
                
                if args.auto_retry:
                    wait_for_quota_reset(logger)
                    # 重置 API 計數器
                    coordinator.api_client.api_call_count = 0
                    continue  # 繼續下載
                else:
                    logger.info("\n💡 提示: 使用 --auto-retry 可以自動等待配額重置後繼續")
                    break
            else:
                # 下載完成
                break
                
        except KeyboardInterrupt:
            logger.warning("\n⚠️  使用者中斷下載")
            progress.save_progress()
            logger.info("💾 進度已保存，下次執行將從中斷點繼續")
            sys.exit(130)
            
        except Exception as e:
            logger.error(f"❌ 下載過程發生錯誤: {e}", exc_info=True)
            progress.save_progress()
            sys.exit(1)
    
    # 最終統計
    stats = result['stats']
    duration = (stats['end_time'] - stats['start_time']).total_seconds()
    
    print("\n" + "="*80)
    print("📊 下載完成統計")
    print("="*80)
    print(f"總資料表數:       {stats['total_tables']}")
    print(f"成功下載:         {stats['completed_tables']}")
    print(f"下載失敗:         {stats['failed_tables']}")
    print(f"─" * 80)
    print(f"總記錄數:         {stats['total_records']:,}")
    print(f"新增記錄:         {stats['new_records']:,}")
    print(f"更新記錄:         {stats['updated_records']:,}")
    print(f"跳過記錄:         {stats['skipped_records']:,}")
    print(f"─" * 80)
    print(f"耗時:             {duration:.2f} 秒 ({duration/60:.1f} 分鐘)")
    print(f"API 使用:         {api_usage['call_count']}/{api_usage['quota']} ({api_usage['usage_percent']}%)")
    print("="*80 + "\n")
    
    if stats['failed_tables'] > 0:
        logger.warning(f"⚠️  部分資料表下載失敗 ({stats['failed_tables']} 個)")
        sys.exit(1)
    elif stats['completed_tables'] < stats['total_tables']:
        logger.info(f"⏸️  下載未完成，下次執行將繼續")
        sys.exit(0)
    else:
        logger.info("✅ 所有資料下載成功")
        # 下載完成後清空進度
        progress.reset_progress(keep_blacklist=True)
        sys.exit(0)


if __name__ == '__main__':
    main()
