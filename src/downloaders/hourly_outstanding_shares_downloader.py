#!/usr/bin/env python3
"""
每小时自动下载流通股数（利用 API 配额每小时重置机制）

功能:
1. 检测 API 配额耗尽 (402 错误)
2. 自动等待到下一个整点
3. 继续下载未完成的股票
4. 提供完整的进度日志
5. 直到所有优先股票下载完成

执行方式:
    python3 src/downloaders/hourly_outstanding_shares_downloader.py --priority-list
    python3 src/downloaders/hourly_outstanding_shares_downloader.py --all
"""

import sys
import os
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from pymongo import MongoClient
from bson.decimal128 import Decimal128
import requests
from typing import Dict, List, Tuple

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class HourlyDownloader:
    """每小时自动下载器"""
    
    def __init__(self, 
                 api_token: str = None,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        
        self.api_token = api_token or os.getenv('FINMIND_API_TOKEN')
        if not self.api_token:
            raise ValueError("请设定 FINMIND_API_TOKEN 环境变量")
        
        self.base_url = "https://api.finmindtrade.com/api/v4/data"
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.logger = self._setup_logger()
        
        # API 速率限制
        self.last_request_time = 0
        self.min_request_interval = 0.6  # 秒
        
        # 配额管理
        self.quota_exhausted = False
        self.quota_reset_time = None
        self.requests_this_hour = 0
        self.successful_this_hour = 0
        self.consecutive_402_errors = 0
    
    def _setup_logger(self) -> logging.Logger:
        """设定日志"""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"hourly_download_{timestamp}.log"
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        self.logger = logger
        return logger
    
    def _rate_limit(self):
        """API 速率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def _to_decimal128(self, value):
        """转换为 Decimal128"""
        if value is None:
            return None
        if isinstance(value, Decimal128):
            return value
        return Decimal128(str(Decimal(str(value))))
    
    def _wait_until_next_hour(self):
        """等待到下一个整点"""
        now = datetime.now()
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        wait_seconds = (next_hour - now).total_seconds()
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"⏰ API 配额已耗尽")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"当前时间: {now.strftime('%H:%M:%S')}")
        self.logger.info(f"下次重试: {next_hour.strftime('%H:%M:%S')}")
        self.logger.info(f"等待时间: {int(wait_seconds/60)} 分钟 {int(wait_seconds%60)} 秒")
        self.logger.info(f"{'='*80}\n")
        
        # 每分钟显示一次倒计时
        while wait_seconds > 0:
            mins = int(wait_seconds / 60)
            secs = int(wait_seconds % 60)
            self.logger.info(f"⏳ 倒计时: {mins:02d}:{secs:02d} (按 Ctrl+C 中断)")
            
            sleep_time = min(60, wait_seconds)
            time.sleep(sleep_time)
            wait_seconds -= sleep_time
        
        # 重置配额计数
        self.quota_exhausted = False
        self.requests_this_hour = 0
        self.successful_this_hour = 0
        self.consecutive_402_errors = 0
        
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"✅ 配额已重置，继续下载...")
        self.logger.info(f"{'='*80}\n")
    
    def download_capital_stock(self, stock_id: str) -> Tuple[float, bool]:
        """
        下载股本数据
        
        Returns:
            (流通股数, 是否配额耗尽)
        """
        self._rate_limit()
        self.requests_this_hour += 1
        
        params = {
            'dataset': 'TaiwanStockBalanceSheet',
            'data_id': stock_id,
            'start_date': '2024-01-01',
            'token': self.api_token
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            
            # 检测 402 配额耗尽
            if response.status_code == 402:
                self.consecutive_402_errors += 1
                self.logger.warning(f"⚠️  {stock_id}: API 配额耗尽 (402)")
                
                # 连续 3 次 402 错误，判定配额耗尽
                if self.consecutive_402_errors >= 3:
                    self.quota_exhausted = True
                    return 0.0, True
                
                return 0.0, False
            
            response.raise_for_status()
            
            # 重置 402 计数器（成功请求）
            self.consecutive_402_errors = 0
            
            data = response.json()
            
            if data.get('status') != 200:
                self.logger.debug(f"API 错误: {data.get('msg')}")
                return 0.0, False
            
            records = data.get('data', [])
            
            if not records:
                self.logger.debug(f"⚠️  {stock_id}: 无资产负债表数据")
                return 0.0, False
            
            # 查找最新股本
            latest_date = max([r['date'] for r in records])
            capital_record = next(
                (r for r in records 
                 if r['date'] == latest_date and r['type'] == 'CapitalStock'),
                None
            )
            
            if not capital_record:
                self.logger.debug(f"⚠️  {stock_id}: 找不到股本数据")
                return 0.0, False
            
            capital_amount = float(capital_record.get('value', 0))
            
            if capital_amount <= 0:
                self.logger.debug(f"⚠️  {stock_id}: 股本金额无效 = {capital_amount}")
                return 0.0, False
            
            # 计算流通股数（千股）
            par_value = 10
            outstanding_shares_k = (capital_amount / par_value) / 1000
            
            self.logger.info(
                f"✅ {stock_id}: 股本 {capital_amount/1e8:,.2f} 亿, "
                f"流通股数 {outstanding_shares_k:,.0f} 千股 ({latest_date})"
            )
            
            self.successful_this_hour += 1
            return outstanding_shares_k, False
            
        except requests.exceptions.RequestException as e:
            if "402" in str(e):
                self.consecutive_402_errors += 1
                if self.consecutive_402_errors >= 3:
                    self.quota_exhausted = True
                    return 0.0, True
            
            self.logger.error(f"❌ {stock_id}: API 请求失败 - {e}")
            return 0.0, False
        except Exception as e:
            self.logger.error(f"❌ {stock_id}: 处理失败 - {e}")
            return 0.0, False
    
    def update_stock(self, stock_id: str, stock_name: str = "") -> Dict:
        """更新单一股票"""
        stats = {
            'stock_id': stock_id,
            'status': 'pending',
            'outstanding_shares': 0,
            'updated': False,
            'quota_exhausted': False
        }
        
        try:
            # 下载股本数据
            outstanding_shares_k, quota_exhausted = self.download_capital_stock(stock_id)
            
            if quota_exhausted:
                stats['status'] = 'quota_exhausted'
                stats['quota_exhausted'] = True
                return stats
            
            if outstanding_shares_k <= 0:
                stats['status'] = 'no_data'
                return stats
            
            stats['outstanding_shares'] = outstanding_shares_k
            
            # 更新数据库
            result = self.db.taiwan_stock_info.update_one(
                {'stock_id': stock_id},
                {
                    '$set': {
                        'outstanding_shares': self._to_decimal128(outstanding_shares_k),
                        'updated_at': datetime.now()
                    }
                },
                upsert=True
            )
            
            stats['updated'] = result.modified_count > 0 or result.upserted_id is not None
            stats['status'] = 'success'
            
        except Exception as e:
            self.logger.error(f"❌ {stock_id}: 处理失败 - {str(e)}")
            stats['status'] = 'error'
            stats['error'] = str(e)
        
        return stats
    
    def _load_priority_list(self) -> List[Tuple[str, str]]:
        """加载优先列表"""
        priority_file = project_root / "data" / "priority_stocks.txt"
        
        if not priority_file.exists():
            self.logger.error(f"找不到优先列表: {priority_file}")
            return []
        
        stock_list = []
        with open(priority_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if parts:
                    stock_id = parts[0].strip()
                    stock_name = parts[1].strip() if len(parts) > 1 else ""
                    stock_list.append((stock_id, stock_name))
        
        return stock_list
    
    def _get_missing_stocks(self, stock_list: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """获取未下载的股票"""
        missing = []
        for stock_id, stock_name in stock_list:
            doc = self.db.taiwan_stock_info.find_one(
                {'stock_id': stock_id},
                {'outstanding_shares': 1}
            )
            if not doc or not doc.get('outstanding_shares'):
                missing.append((stock_id, stock_name))
        
        return missing
    
    def run_continuous(self, priority_list: bool = False, max_hours: int = 24):
        """
        持续运行，每小时下载一批
        
        Args:
            priority_list: 是否使用优先列表
            max_hours: 最多运行小时数（防止无限循环）
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🚀 每小时自动下载器")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"模式: {'优先列表 (50 支核心股票)' if priority_list else '全部股票'}")
        self.logger.info(f"最大运行时间: {max_hours} 小时")
        self.logger.info(f"{'='*80}\n")
        
        hours_elapsed = 0
        total_downloaded = 0
        
        while hours_elapsed < max_hours:
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"📥 第 {hours_elapsed + 1} 小时开始")
            self.logger.info(f"{'='*80}")
            self.logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # 获取待下载列表
            if priority_list:
                all_stocks = self._load_priority_list()
                missing_stocks = self._get_missing_stocks(all_stocks)
            else:
                all_stock_ids = self.db.taiwan_stock_info.distinct('stock_id')
                all_stocks = [(sid, "") for sid in all_stock_ids]
                missing_stocks = self._get_missing_stocks(all_stocks)
            
            if not missing_stocks:
                self.logger.info(f"\n{'='*80}")
                self.logger.info(f"✅ 所有股票都已下载完成！")
                self.logger.info(f"{'='*80}")
                self.logger.info(f"总下载数: {total_downloaded}")
                self.logger.info(f"总耗时: {hours_elapsed} 小时")
                self.logger.info(f"{'='*80}\n")
                break
            
            self.logger.info(f"待下载股票: {len(missing_stocks)} 支\n")
            
            # 逐一下载
            hour_success = 0
            for i, (stock_id, stock_name) in enumerate(missing_stocks, 1):
                display_name = f"{stock_id} {stock_name}" if stock_name else stock_id
                self.logger.info(f"[{i}/{len(missing_stocks)}] {display_name}")
                
                stats = self.update_stock(stock_id, stock_name)
                
                if stats['status'] == 'success':
                    hour_success += 1
                    total_downloaded += 1
                elif stats['status'] == 'quota_exhausted':
                    self.logger.info(f"\n⚠️  配额耗尽于第 {i} 支股票")
                    break
                
                # 检查是否配额耗尽
                if self.quota_exhausted:
                    break
            
            # 小时总结
            self.logger.info(f"\n{'='*80}")
            self.logger.info(f"📊 第 {hours_elapsed + 1} 小时总结")
            self.logger.info(f"{'='*80}")
            self.logger.info(f"本小时下载: {hour_success} 支")
            self.logger.info(f"累计下载: {total_downloaded} 支")
            self.logger.info(f"剩余待下载: {len(missing_stocks) - hour_success} 支")
            self.logger.info(f"{'='*80}\n")
            
            hours_elapsed += 1
            
            # 如果配额耗尽且还有未下载的，等待下一小时
            if self.quota_exhausted and (len(missing_stocks) - hour_success) > 0:
                self._wait_until_next_hour()
            else:
                # 全部完成
                break
        
        # 最终报告
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"🎉 下载任务完成")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"总下载数: {total_downloaded} 支")
        self.logger.info(f"总耗时: {hours_elapsed} 小时")
        self.logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='每小时自动下载流通股数',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
范例:
  # 下载优先列表（核心 50 支股票）
  python3 %(prog)s --priority-list
  
  # 下载所有股票
  python3 %(prog)s --all
  
  # 限制最多运行 6 小时
  python3 %(prog)s --priority-list --max-hours 6
        """
    )
    parser.add_argument('--priority-list', action='store_true',
                        help='使用优先股票列表（核心 50 支）')
    parser.add_argument('--all', action='store_true',
                        help='下载所有股票')
    parser.add_argument('--max-hours', type=int, default=24,
                        help='最大运行小时数（默认 24）')
    
    args = parser.parse_args()
    
    if not (args.priority_list or args.all):
        parser.print_help()
        return
    
    try:
        downloader = HourlyDownloader()
        downloader.run_continuous(
            priority_list=args.priority_list,
            max_hours=args.max_hours
        )
    
    except ValueError as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)


if __name__ == '__main__':
    main()
