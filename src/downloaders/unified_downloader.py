#!/usr/bin/env python3
"""
統一下載主程式
替代所有重複的下載腳本，提供單一進入點

使用範例:
    # 下載所有資料
    python3 unified_downloader.py --all
    
    # 下載指定類別
    python3 unified_downloader.py --categories 技術面 基本面
    
    # 覆蓋下載（不跳過已存在資料）
    python3 unified_downloader.py --all --no-skip
    
    # 詳細日誌
    python3 unified_downloader.py --all --verbose
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# 設定環境變數和路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.downloaders.download_coordinator import DownloadCoordinator
from src.downloaders.table_config import get_all_tables


def setup_logging(verbose: bool = False) -> logging.Logger:
    """設定日誌系統"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # 創建 logs 目錄
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # 日誌檔案名稱（帶時間戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"unified_download_{timestamp}.log"
    
    # 設定格式
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 檔案處理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # 控制台處理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # 根日誌記錄器
    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 靜音第三方 DEBUG 噪音：pymongo 連線池 DEBUG 曾把單一 log 灌到 1.1GB/次、
    # 每小時一檔累積 35GB 逼近磁碟滿。不論 verbose 與否都壓到 WARNING。
    for _noisy in ("pymongo", "urllib3", "requests", "urllib3.connectionpool"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    logger.info(f"📝 日誌檔案: {log_file}")
    return logger


def print_statistics(stats: dict):
    """列印下載統計"""
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
    print(f"驗證錯誤:         {stats['validation_errors']:,}")
    print(f"耗時:             {duration:.2f} 秒")
    print(f"API 使用率:       完成")
    print("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="台股資料統一下載程式 - 整合所有 FinMind 資料下載功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  下載所有資料:        python unified_downloader.py --all
  下載技術面資料:      python unified_downloader.py --categories 技術面
  下載多個類別:        python unified_downloader.py --categories 技術面 基本面 籌碼面
  覆蓋下載:            python unified_downloader.py --all --no-skip
  詳細日誌:            python unified_downloader.py --all --verbose
        """
    )
    
    # 參數設定
    parser.add_argument(
        '--all',
        action='store_true',
        help='下載所有 43 個資料表'
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        choices=['技術面', '基本面', '籌碼面', '衍生性商品', '其他'],
        help='指定下載類別（可多選）'
    )
    
    parser.add_argument(
        '--no-skip',
        action='store_true',
        help='不跳過已存在的資料（覆蓋下載）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細日誌輸出'
    )
    
    parser.add_argument(
        '--mongo-uri',
        default='mongodb://localhost:27017/',
        help='MongoDB 連線 URI（預設: mongodb://localhost:27017/）'
    )
    
    parser.add_argument(
        '--db-name',
        default='tw_stock_analysis',
        help='資料庫名稱（預設: tw_stock_analysis）'
    )
    
    args = parser.parse_args()
    
    # 驗證參數
    if not args.all and not args.categories:
        parser.error("請指定 --all 或 --categories")
    
    # 獲取 API Token
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 錯誤: 未設定 FINMIND_API_TOKEN 環境變數")
        print("\n請執行: export FINMIND_API_TOKEN='your_token_here'")
        sys.exit(1)
    
    # 設定日誌
    logger = setup_logging(args.verbose)
    
    # 啟動資訊
    print("\n" + "="*80)
    print("🚀 台股資料統一下載系統")
    print("="*80)
    print(f"📅 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 模式: {'覆蓋下載' if args.no_skip else '跳過已存在資料'}")
    
    if args.all:
        print(f"📊 範圍: 全部 43 個資料表")
    else:
        print(f"📊 範圍: {', '.join(args.categories)}")
    
    print("="*80 + "\n")
    
    # 初始化下載協調器
    logger.info("初始化下載協調器...")
    coordinator = DownloadCoordinator(
        api_token=api_token,
        mongo_uri=args.mongo_uri,
        db_name=args.db_name,
        logger=logger
    )
    
    # 執行下載
    try:
        skip_existing = not args.no_skip
        categories = None if args.all else args.categories
        
        logger.info("開始下載資料...")
        result = coordinator.download_all(
            categories=categories,
            skip_existing=skip_existing
        )
        
        # 提取統計資料
        stats = result['stats']
        
        # 列印統計
        print_statistics(stats)
        
        # 返回碼
        if stats['failed_tables'] > 0:
            logger.warning(f"⚠️  部分資料表下載失敗 ({stats['failed_tables']} 個)")
            sys.exit(1)
        else:
            logger.info("✅ 所有資料下載成功")
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.warning("\n⚠️  使用者中斷下載")
        sys.exit(130)
        
    except Exception as e:
        logger.error(f"❌ 下載過程發生錯誤: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
