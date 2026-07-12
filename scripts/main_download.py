#!/usr/bin/env python3
"""
台股資料全自動下載系統
完全自動化執行，無需人工干預
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

# 加入專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.downloaders.download_coordinator import DownloadCoordinator
from src.downloaders.table_config import DATA_TABLES


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    設定日誌系統
    
    Args:
        log_dir: 日誌目錄
        
    Returns:
        Logger 物件
    """
    # 確保日誌目錄存在
    os.makedirs(log_dir, exist_ok=True)
    
    # 日誌檔名
    log_file = os.path.join(log_dir, f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    # 設定 Logger
    logger = logging.getLogger("FinMindDownloader")
    logger.setLevel(logging.INFO)
    
    # 清除既有的 handlers
    logger.handlers.clear()
    
    # 檔案 Handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 終端 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"📝 日誌檔案: {log_file}")
    
    return logger


def get_api_token() -> str:
    """
    獲取 API Token
    優先從環境變數，其次從 .env 檔案
    
    Returns:
        API Token
    """
    # 從環境變數
    token = os.environ.get('FINMIND_API_TOKEN')
    if token:
        return token
    
    # 從 .env 檔案
    env_file = project_root / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('FINMIND_API_TOKEN='):
                    token = line.split('=', 1)[1].strip()
                    if token:
                        return token
    
    # 從備份腳本中提取（臨時方案）
    backup_script = project_root / 'backup_20260220' / 'batch_download_all_financials.py'
    if backup_script.exists():
        with open(backup_script, 'r') as f:
            for line in f:
                if 'FINMIND_TOKEN = ' in line:
                    # 提取 token
                    token = line.split('=', 1)[1].strip().strip('"\'')
                    if token:
                        return token
    
    raise ValueError(
        "❌ 找不到 FINMIND_API_TOKEN\n"
        "請設定環境變數: export FINMIND_API_TOKEN=your_token\n"
        "或在 .env 檔案中設定: FINMIND_API_TOKEN=your_token"
    )


def update_data_dictionary(results: dict, logger: logging.Logger):
    """
    更新資料字典文件
    
    Args:
        results: 下載結果
        logger: Logger 物件
    """
    try:
        docs_dir = project_root / 'docs'
        docs_dir.mkdir(exist_ok=True)
        
        dict_file = docs_dir / 'data_dictionary.md'
        
        content = []
        content.append("# 台股資料字典")
        content.append("")
        content.append(f"**更新時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("")
        content.append("---")
        content.append("")
        
        # 統計資訊
        stats = results['stats']
        content.append("## 📊 資料庫統計")
        content.append("")
        content.append(f"- **總資料表數**: {stats['total_tables']}")
        content.append(f"- **已完成下載**: {stats['completed_tables']}")
        content.append(f"- **總記錄數**: {stats['total_records']:,}")
        content.append(f"- **最後下載時間**: {stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        content.append("")
        content.append("---")
        content.append("")
        
        # 各類別詳細資訊
        for category, tables in DATA_TABLES.items():
            content.append(f"## {category}")
            content.append("")
            
            for table in tables:
                # 從結果中找到對應的資料
                table_result = next(
                    (r for r in results['results'] if r['name'] == table['name']),
                    None
                )
                
                status_icon = "✅" if table_result and table_result['status'] == 'success' else "❌"
                
                content.append(f"### {status_icon} {table['name']}")
                content.append("")
                content.append(f"**說明**: {table.get('description', '無')}")
                content.append("")
                content.append(f"- **Dataset**: `{table['dataset']}`")
                content.append(f"- **Collection**: `{table['collection']}`")
                content.append(f"- **需要股票代碼**: {'是' if table.get('needs_symbols') else '否'}")
                
                if table_result and table_result['status'] == 'success':
                    content.append(f"- **記錄數**: {table_result.get('total_records', 0):,}")
                    content.append(f"- **狀態**: ✅ 已下載")
                else:
                    content.append(f"- **狀態**: ❌ 未下載或失敗")
                
                # 索引資訊
                if table.get('indexes'):
                    content.append(f"- **索引**: {', '.join([f'`{idx[0]}`' for idx in table['indexes']])}")
                
                # 唯一鍵
                if table.get('unique_keys'):
                    content.append(f"- **唯一鍵**: {', '.join([f'`{key}`' for key in table['unique_keys']])}")
                
                content.append("")
        
        # API 使用統計
        api_usage = results['api_usage']
        content.append("---")
        content.append("")
        content.append("## 🔌 API 使用統計")
        content.append("")
        content.append(f"- **總調用次數**: {api_usage['call_count']}")
        content.append(f"- **配額**: {api_usage['quota']}")
        content.append(f"- **使用率**: {api_usage['usage_percent']}%")
        content.append(f"- **剩餘**: {api_usage['remaining']}")
        content.append("")
        
        # 寫入檔案
        with open(dict_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        logger.info(f"✅ 資料字典已更新: {dict_file}")
        
    except Exception as e:
        logger.error(f"❌ 更新資料字典失敗: {e}")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description='台股資料全自動下載系統',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 下載所有資料
  python main_download.py
  
  # 下載指定類別
  python main_download.py --categories 技術面 籌碼面
  
  # 強制重新下載（不跳過已存在資料）
  python main_download.py --force
  
  # 指定 MongoDB URI
  python main_download.py --mongo mongodb://localhost:27017/
        """
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        choices=['技術面', '籌碼面', '基本面', '衍生性金融商品', '其他'],
        help='指定要下載的類別'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='強制重新下載，不跳過已存在的資料'
    )
    
    parser.add_argument(
        '--mongo',
        default='mongodb://localhost:27017/',
        help='MongoDB 連線 URI'
    )
    
    parser.add_argument(
        '--db',
        default='tw_stock_analysis',
        help='資料庫名稱'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日誌等級'
    )
    
    args = parser.parse_args()
    
    # 設定日誌
    logger = setup_logging()
    logger.setLevel(getattr(logging, args.log_level))
    
    try:
        # 獲取 API Token
        logger.info("🔑 獲取 API Token...")
        api_token = get_api_token()
        logger.info("✅ API Token 已載入")
        
        # 初始化下載協調器
        logger.info(f"🔗 連線 MongoDB: {args.mongo}")
        coordinator = DownloadCoordinator(
            api_token=api_token,
            mongo_uri=args.mongo,
            db_name=args.db,
            logger=logger
        )
        
        # 開始下載
        skip_existing = not args.force
        results = coordinator.download_all(
            categories=args.categories,
            skip_existing=skip_existing
        )
        
        # 更新資料字典
        logger.info("\n📚 更新資料字典...")
        update_data_dictionary(results, logger)
        
        # 關閉連線
        coordinator.close()
        
        # 結束
        logger.info("\n🎉 所有任務執行完畢！")
        
        # 返回狀態碼
        if results['stats']['failed_tables'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.warning("\n⚠️  使用者中斷執行")
        sys.exit(130)
        
    except Exception as e:
        logger.error(f"\n❌ 執行失敗: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
