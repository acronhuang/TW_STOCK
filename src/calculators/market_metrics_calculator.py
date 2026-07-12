#!/usr/bin/env python3
"""
P2: 市值與換手率計算器

計算並儲存每日市場指標:
1. market_cap (市值) = 收盤價 × 流通股數
2. turnover_rate (換手率) = 成交量 / 流通股數 × 100%

數據來源:
- 收盤價: stock_price.close
- 成交量: stock_price.volume
- 流通股數: taiwan_stock_info.outstanding_shares (單位:千股)

執行方式:
    python3 src/calculators/market_metrics_calculator.py --stock-id 2330 --dry-run
    python3 src/calculators/market_metrics_calculator.py --all --execute
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
from typing import Dict, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class MarketMetricsCalculator:
    """市值與換手率計算器"""
    
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
        log_file = log_dir / f"market_metrics_{timestamp}.log"
        
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
        """轉換為 Decimal128"""
        return Decimal128(Decimal(str(round(value, 2))))
    
    def get_outstanding_shares(self, stock_id: str) -> float:
        """
        獲取流通股數
        
        Returns:
            流通股數（單位：股）
        """
        # 從 taiwan_stock_info 獲取
        info = self.db.taiwan_stock_info.find_one(
            {"stock_id": stock_id},
            {"outstanding_shares": 1}
        )
        
        if info and 'outstanding_shares' in info:
            # outstanding_shares 單位是千股，需要乘以1000
            shares_in_thousands = self._to_float(info['outstanding_shares'])
            return shares_in_thousands * 1000
        
        # 如果沒有數據，嘗試從 FinMind 推算
        # 註：這裡可以整合 TaiwanStockInfo API
        self.logger.warning(f"⚠️  {stock_id}: 沒有流通股數資料")
        return 0.0
    
    def calculate_stock_metrics(self, stock_id: str, dry_run: bool = True) -> Dict:
        """
        計算單一股票的市值和換手率
        
        Args:
            stock_id: 股票代碼
            dry_run: 是否為預覽模式
            
        Returns:
            統計資訊
        """
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"計算 {stock_id} 市值與換手率")
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
            # 1. 獲取流通股數
            outstanding_shares = self.get_outstanding_shares(stock_id)
            
            if outstanding_shares <= 0:
                self.logger.warning(f"⚠️  流通股數無效: {outstanding_shares}")
                stats['status'] = 'no_shares_data'
                return stats
            
            self.logger.info(f"流通股數: {outstanding_shares:,.0f} 股 ({outstanding_shares/1000:,.0f}千股)")
            
            # 2. 獲取所有股價記錄
            prices = list(self.db.stock_price.find(
                {"symbol": stock_id},
                {"_id": 1, "date": 1, "close": 1, "volume": 1}
            ).sort("date", 1))
            
            stats['total_records'] = len(prices)
            
            if not prices:
                self.logger.warning(f"⚠️  沒有價格數據")
                stats['status'] = 'no_price_data'
                return stats
            
            self.logger.info(f"價格記錄: {len(prices):,} 筆")
            
            # 3. 計算每日指標
            updates = []
            
            for price in prices:
                close = self._to_float(price.get('close', 0))
                volume = self._to_float(price.get('volume', 0))
                
                if close <= 0:
                    continue
                
                # 計算市值 (單位：元)
                market_cap = close * outstanding_shares
                
                # 計算換手率 (%)
                turnover_rate = (volume / outstanding_shares * 100) if outstanding_shares > 0 else 0
                
                updates.append(
                    UpdateOne(
                        {"_id": price['_id']},
                        {"$set": {
                            "market_cap": self._to_decimal128(market_cap),
                            "turnover_rate": self._to_decimal128(turnover_rate)
                        }}
                    )
                )
            
            stats['calculated'] = len(updates)
            
            # 4. 批次更新
            if not dry_run and updates:
                try:
                    result = self.db.stock_price.bulk_write(updates, ordered=False)
                    stats['updated'] = result.modified_count
                    stats['status'] = 'success'
                    self.logger.info(f"✅ 更新成功: {stats['updated']:,} 筆")
                    
                except BulkWriteError as e:
                    error_msg = f"批次更新失敗: {e.details}"
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
        self.logger.info(f"{'='*80}\n")
        
        return stats
    
    def calculate_all_metrics(self, dry_run: bool = True, limit: int = None) -> Dict:
        """計算所有股票的市值和換手率"""
        self.logger.info("\n" + "="*80)
        self.logger.info("🚀 市值與換手率計算器")
        self.logger.info("="*80)
        self.logger.info(f"模式: {'預覽模式' if dry_run else '實際執行模式'}")
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
            
            stats = self.calculate_stock_metrics(stock_id, dry_run)
            
            summary['total_records'] += stats['total_records']
            summary['total_updated'] += stats['updated']
            
            if stats['status'] == 'success' or stats['status'] == 'dry_run':
                summary['success'] += 1
            elif stats['status'] in ['no_price_data', 'no_shares_data']:
                summary['no_data'] += 1
            else:
                summary['errors'] += 1
                failed_stocks.append(stock_id)
        
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
            self.logger.info(f"\n⚠️  失敗股票: {', '.join(failed_stocks[:20])}")
        
        coverage = summary['total_updated'] / summary['total_records'] * 100 if summary['total_records'] > 0 else 0
        self.logger.info(f"\n覆蓋率: {coverage:.2f}%")
        self.logger.info("="*80)
        
        if dry_run:
            self.logger.info("\n⚠️  這是預覽模式")
        else:
            self.logger.info("\n✅ 市值與換手率計算完成！")
        
        self.logger.info("="*80 + "\n")


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description="P2: 市值與換手率計算器"
    )
    
    parser.add_argument('--stock-id', help='指定股票代碼')
    parser.add_argument('--all', action='store_true', help='計算所有股票')
    parser.add_argument('--limit', type=int, help='限制股票數量')
    parser.add_argument('--dry-run', action='store_true', help='預覽模式')
    parser.add_argument('--execute', action='store_true', help='實際執行')
    parser.add_argument('--mongo-uri', default='mongodb://localhost:27017/')
    parser.add_argument('--db-name', default='tw_stock_analysis')
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("❌ 請指定 --dry-run 或 --execute")
        sys.exit(1)
    
    if not args.stock_id and not args.all:
        print("❌ 請指定 --stock-id 或 --all")
        sys.exit(1)
    
    if args.execute:
        response = input("⚠️  確認執行？請輸入 'YES': ")
        if response != 'YES':
            sys.exit(0)
    
    calculator = MarketMetricsCalculator(args.mongo_uri, args.db_name)
    
    if args.stock_id:
        calculator.calculate_stock_metrics(args.stock_id, dry_run=args.dry_run)
    else:
        calculator.calculate_all_metrics(dry_run=args.dry_run, limit=args.limit)


if __name__ == '__main__':
    main()
