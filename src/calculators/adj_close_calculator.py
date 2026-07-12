#!/usr/bin/env python3
"""
P1: 調整後收盤價 (Adjusted Close) 計算器

調整後收盤價會根據以下事件回溯調整歷史股價：
1. 現金股利（除息）
2. 股票股利（除權）
3. 股票分割

執行方式:
    python3 src/calculators/adj_close_calculator.py --stock-id 2330 --dry-run  # 預覽
    python3 src/calculators/adj_close_calculator.py --all --execute  # 計算所有股票
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from typing import List, Dict

# 設定路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class AdjustedCloseCalculator:
    """調整後收盤價計算器"""
    
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
        log_file = log_dir / f"adj_close_calc_{timestamp}.log"
        
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
    
    def _decimal_to_float(self, value):
        """將 Decimal128 轉為 float 以便計算"""
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        elif isinstance(value, Decimal):
            return float(value)
        return float(value) if value else 0.0
    
    def _float_to_decimal128(self, value: float):
        """將 float 轉為 Decimal128"""
        return Decimal128(Decimal(str(round(value, 4))))
    
    def get_dividend_events(self, stock_id: str) -> List[Dict]:
        """
        獲取股票的除權息事件
        
        Returns:
            排序後的除權息事件列表 [{date, cash_dividend, stock_dividend}, ...]
        """
        # 從 dividend_detail 獲取股利資料
        dividends = list(self.db.dividend_detail.find(
            {"stock_id": stock_id},
            {
                "date": 1,
                "cash_ex_dividend_date": 1,
                "stock_ex_dividend_date": 1,
                "cash_earnings_distribution": 1,
                "cash_statutory_surplus": 1,
                "stock_earnings_distribution": 1,
                "stock_statutory_surplus": 1
            }
        ).sort("date", 1))
        
        events = []
        
        for div in dividends:
            # 除息日（現金股利）
            cash_ex_date_str = div.get('cash_ex_dividend_date')
            if cash_ex_date_str and cash_ex_date_str.strip():  # 確保非空
                try:
                    ex_date = datetime.strptime(cash_ex_date_str, '%Y-%m-%d')
                    cash_div = self._decimal_to_float(div.get('cash_earnings_distribution', 0)) + \
                              self._decimal_to_float(div.get('cash_statutory_surplus', 0))
                    
                    if cash_div > 0:
                        events.append({
                            'date': ex_date,
                            'type': 'cash_dividend',
                            'amount': cash_div
                        })
                except ValueError as e:
                    self.logger.debug(f"無法解析現金除息日 '{cash_ex_date_str}': {e}")
                except Exception as e:
                    self.logger.warning(f"處理現金股利時發生錯誤: {e}")
            
            # 除權日（股票股利）
            stock_ex_date_str = div.get('stock_ex_dividend_date')
            if stock_ex_date_str and stock_ex_date_str.strip():  # 確保非空
                try:
                    ex_date = datetime.strptime(stock_ex_date_str, '%Y-%m-%d')
                    stock_div = self._decimal_to_float(div.get('stock_earnings_distribution', 0)) + \
                               self._decimal_to_float(div.get('stock_statutory_surplus', 0))
                    
                    if stock_div > 0:
                        events.append({
                            'date': ex_date,
                            'type': 'stock_dividend',
                            'amount': stock_div
                        })
                except ValueError as e:
                    self.logger.debug(f"無法解析股票除權日 '{stock_ex_date_str}': {e}")
                except Exception as e:
                    self.logger.warning(f"處理股票股利時發生錯誤: {e}")
        
        # 按日期排序（從新到舊，因為我們要從最新回推）
        events.sort(key=lambda x: x['date'], reverse=True)
        
        return events
    
    def calculate_adjusted_close(self, stock_id: str, dry_run: bool = True) -> Dict:
        """
        計算單一股票的調整後收盤價
        
        調整公式：
        - 現金股利: adj_close_before = adj_close_after * (close_before - cash_dividend) / close_before
        - 股票股利: adj_close_before = adj_close_after * 10 / (10 + stock_dividend)
        
        Args:
            stock_id: 股票代碼
            dry_run: 是否為預覽模式
            
        Returns:
            計算統計
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"計算 {stock_id} 的調整後收盤價")
        self.logger.info(f"{'='*80}\n")
        
        # 獲取股價資料（按日期降序）
        # 注意：stock_price 集合使用 'symbol' 欄位
        prices = list(self.db.stock_price.find(
            {"symbol": stock_id},
            {"date": 1, "close": 1, "closePrice": 1}
        ).sort("date", -1))
        
        if not prices:
            self.logger.warning(f"⚠️  找不到股價資料: {stock_id}")
            return {'status': 'error', 'message': 'No price data'}
        
        self.logger.info(f"股價記錄數: {len(prices)}")
        
        # 獲取除權息事件
        events = self.get_dividend_events(stock_id)
        self.logger.info(f"除權息事件數: {len(events)}")
        
        if events:
            for event in events[:5]:  # 顯示最近 5 個事件
                self.logger.info(f"  {event['date'].strftime('%Y-%m-%d')}: "
                               f"{event['type']} = {event['amount']:.2f}")
        
        # 計算調整後價格
        # 初始化：最新的一天，adjusted close = close
        adj_factor = 1.0
        updates = []
        
        for i, price in enumerate(prices):
            date = price['date']
            
            # 確保 date 是 datetime 對象
            if isinstance(date, str):
                try:
                    date = datetime.strptime(date, '%Y-%m-%d')
                except ValueError:
                    self.logger.warning(f"⚠️  無法解析日期: {date}")
                    continue
            
            # 兼容舊欄位名稱
            close = self._decimal_to_float(price.get('close') or price.get('closePrice'))
            
            if close <= 0:
                self.logger.warning(f"⚠️  {date.strftime('%Y-%m-%d')} 收盤價異常: {close}")
                continue
            
            # 檢查是否有除權息事件
            for event in events:
                # 安全的日期比較：將兩個 datetime 都轉換為 date 對象
                event_date = event['date'].date() if isinstance(event['date'], datetime) else event['date']
                price_date = date.date() if isinstance(date, datetime) else date
                
                if event_date == price_date:
                    if event['type'] == 'cash_dividend':
                        # 現金股利調整
                        adj_factor *= (close - event['amount']) / close
                        self.logger.debug(f"  {date.strftime('%Y-%m-%d')}: 除息 {event['amount']:.2f}, "
                                        f"調整因子: {adj_factor:.6f}")
                    
                    elif event['type'] == 'stock_dividend':
                        # 股票股利調整（除以「股利/10 + 1」）
                        adj_factor *= 10.0 / (10.0 + event['amount'])
                        self.logger.debug(f"  {date.strftime('%Y-%m-%d')}: 除權 {event['amount']:.2f}, "
                                        f"調整因子: {adj_factor:.6f}")
            
            # 計算調整後收盤價
            adj_close = close * adj_factor
            
            updates.append({
                '_id': price['_id'],
                'adj_close': self._float_to_decimal128(adj_close),
                'adjustment_factor': self._float_to_decimal128(adj_factor)
            })
        
        # 執行更新
        stats = {
            'stock_id': stock_id,
            'total_records': len(prices),
            'calculated': len(updates),
            'updated': 0,
            'errors': 0
        }
        
        if not dry_run:
            for update in updates:
                try:
                    self.db.stock_price.update_one(
                        {"_id": update['_id']},
                        {"$set": {
                            "adj_close": update['adj_close'],
                            "adjustment_factor": update['adjustment_factor']
                        }}
                    )
                    stats['updated'] += 1
                except Exception as e:
                    self.logger.error(f"更新失敗: {e}")
                    stats['errors'] += 1
        else:
            stats['updated'] = len(updates)
        
        self.logger.info(f"\n✅ 完成 {stock_id}")
        self.logger.info(f"   計算: {stats['calculated']:,} 筆")
        self.logger.info(f"   {'將更新' if dry_run else '已更新'}: {stats['updated']:,} 筆\n")
        
        return stats
    
    def calculate_all(self, dry_run: bool = True, limit: int = None) -> Dict:
        """計算所有股票的調整後收盤價"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 開始計算調整後收盤價 (Adjusted Close)")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行模式'}")
        self.logger.info(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("="*80 + "\n")
        
        # 獲取所有股票代碼
        # 注意：stock_price 集合使用 'symbol' 欄位
        stock_ids = self.db.stock_price.distinct('symbol')
        
        if limit:
            stock_ids = stock_ids[:limit]
        
        self.logger.info(f"股票總數: {len(stock_ids)}\n")
        
        all_stats = []
        success_count = 0
        error_count = 0
        
        for i, stock_id in enumerate(stock_ids, 1):
            self.logger.info(f"[{i}/{len(stock_ids)}] 處理 {stock_id}")
            
            try:
                stats = self.calculate_adjusted_close(stock_id, dry_run)
                all_stats.append(stats)
                
                if stats.get('status') != 'error':
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                self.logger.error(f"❌ {stock_id} 計算失敗: {e}")
                error_count += 1
        
        # 總結
        self._print_summary(all_stats, success_count, error_count, dry_run)
        
        return {
            'total': len(stock_ids),
            'success': success_count,
            'errors': error_count,
            'details': all_stats
        }
    
    def _print_summary(self, all_stats: List, success: int, errors: int, dry_run: bool):
        """列印總結報告"""
        total_records = sum(s.get('calculated', 0) for s in all_stats)
        
        self.logger.info("\n" + "="*80)
        self.logger.info("📊 計算總結報告")
        self.logger.info("="*80)
        self.logger.info(f"股票總數: {len(all_stats)}")
        self.logger.info(f"成功: {success}")
        self.logger.info(f"失敗: {errors}")
        self.logger.info(f"總記錄數: {total_records:,}")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式，尚未實際修改數據")
            self.logger.info("如要實際執行，請使用: --execute 參數")
        else:
            self.logger.info("\n✅ 計算完成！所有股票的 adj_close 已更新")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P1: 計算調整後收盤價 (Adjusted Close)"
    )
    
    parser.add_argument(
        '--stock-id',
        help='計算單一股票'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='計算所有股票'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='限制處理股票數量（測試用）'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='預覽模式（不實際修改數據）'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='實際執行計算'
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
    if not args.stock_id and not args.all:
        print("❌ 錯誤: 請指定 --stock-id 或 --all")
        sys.exit(1)
    
    if not args.dry_run and not args.execute:
        print("❌ 錯誤: 請指定 --dry-run 或 --execute")
        print("\n使用 --dry-run 先預覽")
        sys.exit(1)
    
    if args.execute and args.all:
        print("\n⚠️  警告: 您即將計算並更新所有股票的調整後收盤價！")
        response = input("請輸入 'YES' 確認繼續: ")
        if response != 'YES':
            print("❌ 已取消")
            sys.exit(0)
    
    # 執行計算
    calculator = AdjustedCloseCalculator(args.mongo_uri, args.db_name)
    
    if args.stock_id:
        calculator.calculate_adjusted_close(args.stock_id, dry_run=args.dry_run)
    else:
        calculator.calculate_all(dry_run=args.dry_run, limit=args.limit)


if __name__ == '__main__':
    main()
