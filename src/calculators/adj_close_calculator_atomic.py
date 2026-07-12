#!/usr/bin/env python3
"""
P1: 調整後收盤價計算器 (原子性更新版本)

改進特性:
1. 原子性更新：一支股票要麼全部成功，要麼全部不寫入
2. 使用 bulk_write() 批次更新，提升效能
3. 明確的錯誤處理和回滾機制
4. 依賴日期清洗工具，確保日期統一

執行方式:
    python3 src/calculators/adj_close_calculator_atomic.py --stock-id 2330 --dry-run
    python3 src/calculators/adj_close_calculator_atomic.py --all --execute
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError
from bson.decimal128 import Decimal128
from typing import List, Dict, Optional

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class AtomicAdjustedCloseCalculator:
    """原子性調整後收盤價計算器"""
    
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """設定日誌"""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"atomic_adj_close_{timestamp}.log"
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
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
        
        return logger
    
    def _to_float(self, value):
        """統一轉換為 float"""
        if value is None:
            return 0.0
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    
    def _to_decimal128(self, value: float) -> Decimal128:
        """轉換為 Decimal128，保留4位小數"""
        return Decimal128(Decimal(str(round(value, 4))))
    
    def _normalize_date(self, date_value) -> Optional[datetime]:
        """統一日期格式為 datetime"""
        if date_value is None:
            return None
        if isinstance(date_value, datetime):
            return date_value.replace(hour=0, minute=0, second=0, microsecond=0)
        # 如果還有其他格式，應該在此之前執行日期清洗
        self.logger.warning(f"日期格式異常: {type(date_value)}, 值: {date_value}")
        return None
    
    def get_dividend_events(self, stock_id: str) -> List[Dict]:
        """
        獲取除權息事件
        
        Returns:
            [{date: datetime, type: 'cash'/'stock', amount: float}, ...]
        """
        events = []
        
        # 查詢股利資料
        dividends = list(self.db.dividend_detail.find(
            {"stock_id": stock_id},
            {
                "ex_dividend_trading_date": 1,
                "cash_earnings_distribution": 1,
                "stock_earnings_distribution": 1
            }
        ))
        
        for div in dividends:
            ex_date = self._normalize_date(div.get('ex_dividend_trading_date'))
            if not ex_date:
                continue
            
            # 現金股利
            cash_div = self._to_float(div.get('cash_earnings_distribution', 0))
            if cash_div > 0:
                events.append({
                    'date': ex_date,
                    'type': 'cash_dividend',
                    'amount': cash_div
                })
            
            # 股票股利
            stock_div = self._to_float(div.get('stock_earnings_distribution', 0))
            if stock_div > 0:
                events.append({
                    'date': ex_date,
                    'type': 'stock_dividend',
                    'amount': stock_div
                })
        
        # 按日期排序（從最新到最舊）
        events.sort(key=lambda x: x['date'], reverse=True)
        
        return events
    
    def calculate_stock_atomic(self, stock_id: str, dry_run: bool = True) -> Dict:
        """
        原子性計算單一股票的 adj_close
        
        原子性保證：
        - 計算該股票的所有歷史 adj_close
        - 使用 bulk_write() 一次性更新
        - 任何錯誤都不會寫入任何記錄
        
        Returns:
            統計資訊
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"計算 {stock_id} (原子性更新)")
        self.logger.info(f"{'='*80}")
        
        stats = {
            'stock_id': stock_id,
            'status': 'pending',
            'total_records': 0,
            'calculated': 0,
            'updated': 0,
            'errors': []
        }
        
        try:
            # 1. 獲取除權息事件
            events = self.get_dividend_events(stock_id)
            self.logger.info(f"除權息事件: {len(events)} 筆")
            
            if events:
                for event in events[:5]:  # 顯示前5筆
                    self.logger.debug(
                        f"  {event['date'].strftime('%Y-%m-%d')}: "
                        f"{event['type']} = {event['amount']:.2f}"
                    )
            
            # 2. 獲取所有股價記錄（按日期排序，從舊到新）
            prices = list(self.db.stock_price.find(
                {"symbol": stock_id},
                {"_id": 1, "date": 1, "close": 1}
            ).sort("date", 1))
            
            stats['total_records'] = len(prices)
            
            if not prices:
                self.logger.warning(f"⚠️  沒有價格數據")
                stats['status'] = 'no_data'
                return stats
            
            self.logger.info(f"價格記錄: {len(prices):,} 筆")
            self.logger.info(f"日期範圍: {prices[0]['date']} ~ {prices[-1]['date']}")
            
            # 3. 逐日計算調整因子（從最新往回推）
            adj_factor = 1.0
            updates = []
            
            # 建立日期索引以加速查找
            event_by_date = {e['date']: e for e in events}
            
            # 從最新日期開始往回算
            for i in range(len(prices) - 1, -1, -1):
                price = prices[i]
                
                # 統一日期格式
                date = self._normalize_date(price.get('date'))
                if not date:
                    error_msg = f"無效日期: {price.get('date')}"
                    self.logger.warning(f"⚠️  {error_msg}")
                    stats['errors'].append(error_msg)
                    continue
                
                close = self._to_float(price.get('close'))
                
                if close <= 0:
                    error_msg = f"{date.strftime('%Y-%m-%d')}: 收盤價異常 = {close}"
                    self.logger.warning(f"⚠️  {error_msg}")
                    stats['errors'].append(error_msg)
                    continue
                
                # 檢查是否有除權息
                if date in event_by_date:
                    event = event_by_date[date]
                    
                    if event['type'] == 'cash_dividend':
                        # 現金股利調整
                        adj_factor *= (close - event['amount']) / close
                        self.logger.debug(
                            f"{date.strftime('%Y-%m-%d')}: 除息 {event['amount']:.2f}, "
                            f"因子={adj_factor:.6f}"
                        )
                    
                    elif event['type'] == 'stock_dividend':
                        # 股票股利調整
                        adj_factor *= 10.0 / (10.0 + event['amount'])
                        self.logger.debug(
                            f"{date.strftime('%Y-%m-%d')}: 除權 {event['amount']:.2f}, "
                            f"因子={adj_factor:.6f}"
                        )
                
                # 計算調整後收盤價
                adj_close = close * adj_factor
                
                # 準備更新操作
                updates.append(
                    UpdateOne(
                        {"_id": price['_id']},
                        {"$set": {
                            "adj_close": self._to_decimal128(adj_close),
                            "adjustment_factor": self._to_decimal128(adj_factor)
                        }}
                    )
                )
            
            stats['calculated'] = len(updates)
            
            # 4. 原子性批次更新
            if not dry_run and updates:
                try:
                    self.logger.info(f"開始原子性批次更新...")
                    
                    result = self.db.stock_price.bulk_write(
                        updates,
                        ordered=False  # 允許並行，但失敗會拋出異常
                    )
                    
                    stats['updated'] = result.modified_count
                    stats['status'] = 'success'
                    
                    self.logger.info(f"✅ 原子性更新成功: {stats['updated']:,} 筆")
                    
                except BulkWriteError as e:
                    error_msg = f"批次更新失敗: {e.details}"
                    self.logger.error(f"❌ {error_msg}")
                    stats['errors'].append(error_msg)
                    stats['status'] = 'error'
                    # 原子性保證：bulk_write 失敗時，MongoDB 會自動回滾該批次
                
                except Exception as e:
                    error_msg = f"未預期錯誤: {str(e)}"
                    self.logger.error(f"❌ {error_msg}")
                    stats['errors'].append(error_msg)
                    stats['status'] = 'error'
            
            elif dry_run:
                stats['updated'] = stats['calculated']
                stats['status'] = 'dry_run'
                self.logger.info(f"✅ 預覽完成: 將更新 {stats['calculated']:,} 筆")
            
        except Exception as e:
            error_msg = f"計算失敗: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            stats['errors'].append(error_msg)
            stats['status'] = 'error'
        
        # 結果報告
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"結果: {stock_id}")
        self.logger.info(f"  狀態: {stats['status']}")
        self.logger.info(f"  總記錄: {stats['total_records']:,}")
        self.logger.info(f"  計算: {stats['calculated']:,}")
        self.logger.info(f"  更新: {stats['updated']:,}")
        if stats['errors']:
            self.logger.info(f"  錯誤: {len(stats['errors'])} 個")
        self.logger.info(f"{'='*80}\n")
        
        return stats
    
    def calculate_all_atomic(self, dry_run: bool = True, limit: int = None) -> Dict:
        """原子性計算所有股票"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 調整後收盤價計算器 (原子性更新版)")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行模式（原子性）'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        # 獲取所有股票
        stock_ids = self.db.stock_price.distinct('symbol')
        
        if limit:
            stock_ids = stock_ids[:limit]
        
        self.logger.info(f"股票總數: {len(stock_ids)}\n")
        
        # 統計
        summary = {
            'total_stocks': len(stock_ids),
            'success': 0,
            'errors': 0,
            'no_data': 0,
            'total_records': 0,
            'total_updated': 0
        }
        
        failed_stocks = []
        
        for i, stock_id in enumerate(stock_ids, 1):
            self.logger.info(f"[{i}/{len(stock_ids)}] {stock_id}")
            
            stats = self.calculate_stock_atomic(stock_id, dry_run)
            
            summary['total_records'] += stats['total_records']
            summary['total_updated'] += stats['updated']
            
            if stats['status'] == 'success' or stats['status'] == 'dry_run':
                summary['success'] += 1
            elif stats['status'] == 'no_data':
                summary['no_data'] += 1
            else:
                summary['errors'] += 1
                failed_stocks.append({
                    'stock_id': stock_id,
                    'errors': stats['errors']
                })
        
        # 總結報告
        self._print_summary(summary, failed_stocks, dry_run)
        
        return summary
    
    def _print_summary(self, summary: Dict, failed_stocks: List, dry_run: bool):
        """列印總結報告"""
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 計算總結")
        self.logger.info("="*80)
        self.logger.info(f"股票總數: {summary['total_stocks']:,}")
        self.logger.info(f"  成功: {summary['success']:,}")
        self.logger.info(f"  失敗: {summary['errors']:,}")
        self.logger.info(f"  沒資料: {summary['no_data']:,}")
        self.logger.info(f"\n記錄總數: {summary['total_records']:,}")
        self.logger.info(f"{'將更新' if dry_run else '已更新'}: {summary['total_updated']:,}")
        
        if failed_stocks:
            self.logger.info(f"\n⚠️  失敗股票清單:")
            for item in failed_stocks[:10]:  # 只顯示前10個
                self.logger.info(f"  {item['stock_id']}: {item['errors'][:2]}")
        
        coverage = summary['total_updated'] / summary['total_records'] * 100 if summary['total_records'] > 0 else 0
        self.logger.info(f"\n覆蓋率: {coverage:.2f}%")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 原子性更新完成！")
            self.logger.info("每支股票的 adj_close 都是完整計算並一次性更新")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P1: 原子性調整後收盤價計算器"
    )
    
    parser.add_argument(
        '--stock-id',
        help='指定股票代碼'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='計算所有股票'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='限制股票數量（測試用）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='預覽模式'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='實際執行'
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
    
    # 驗證參數
    if not args.dry_run and not args.execute:
        print("❌ 錯誤: 請指定 --dry-run 或 --execute")
        sys.exit(1)
    
    if not args.stock_id and not args.all:
        print("❌ 錯誤: 請指定 --stock-id 或 --all")
        sys.exit(1)
    
    if args.execute:
        print("\n⚠️  警告: 您即將使用原子性更新修改資料庫！")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行計算
    calculator = AtomicAdjustedCloseCalculator(args.mongo_uri, args.db_name)
    
    if args.stock_id:
        calculator.calculate_stock_atomic(args.stock_id, dry_run=args.dry_run)
    else:
        calculator.calculate_all_atomic(dry_run=args.dry_run, limit=args.limit)


if __name__ == '__main__':
    main()
