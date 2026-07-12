#!/usr/bin/env python3
"""
還原權值計算工具
計算並儲存股票的還原權值因子
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from decimal import Decimal

# 加入專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/adjustment_factor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def calculate_adjustment_factors():
    """
    計算還原權值因子
    
    根據股利資料計算每個交易日的還原權值因子
    公式: adjustment_factor = (price_before_ex + cash_dividend + stock_dividend_value) / price_after_ex
    """
    logger.info("\n" + "="*80)
    logger.info("🔄 計算還原權值因子")
    logger.info("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 檢查必要的集合
    if 'dividend_results' not in db.list_collection_names():
        logger.error("❌ 找不到 dividend_results 集合")
        return False
    
    if 'stock_price' not in db.list_collection_names():
        logger.error("❌ 找不到 stock_price 集合")
        return False
    
    dividends = db.dividend_results
    prices = db.stock_price
    
    # 獲取所有股利資料
    dividend_records = list(dividends.find({}))
    logger.info(f"找到 {len(dividend_records)} 筆股利資料")
    
    if len(dividend_records) == 0:
        logger.warning("⚠️  沒有股利資料，無法計算還原權值因子")
        return False
    
    updated_count = 0
    error_count = 0
    
    for dividend in dividend_records:
        try:
            symbol = dividend.get('stock_id') or dividend.get('symbol')
            ex_dividend_date = dividend.get('date') or dividend.get('exDividendDate')
            
            if not symbol or not ex_dividend_date:
                continue
            
            # 提取股利資料
            cash_dividend = extract_decimal(dividend.get('cashDividend', 0))
            stock_dividend = extract_decimal(dividend.get('stockDividend', 0))
            
            if cash_dividend == 0 and stock_dividend == 0:
                continue
            
            # 查找除權息前一天的收盤價
            # dividend_results 的 date 是字串格式 'YYYY-MM-DD'
            # stock_price 的 date 是 ISODate 格式
            # 需要將字串轉換為 datetime 進行比較
            from datetime import datetime as dt
            try:
                ex_date_dt = dt.strptime(ex_dividend_date, '%Y-%m-%d')
            except:
                continue
            
            price_before = prices.find_one(
                {'symbol': symbol, 'date': {'$lt': ex_date_dt}},
                sort=[('date', -1)]
            )
            
            # 查找除權息當天或之後的收盤價
            price_after = prices.find_one(
                {'symbol': symbol, 'date': {'$gte': ex_date_dt}},
                sort=[('date', 1)]
            )
            
            if not price_before or not price_after:
                logger.debug(f"找不到 {symbol} 在 {ex_dividend_date} 前後的價格資料")
                continue
            
            close_before = extract_decimal(price_before.get('close'))
            close_after = extract_decimal(price_after.get('close'))
            
            if not close_before or not close_after or close_after == 0:
                continue
            
            # 計算除權息參考價
            # 除權息參考價 = (前一日收盤價 - 現金股利) / (1 + 股票股利/10)
            stock_dividend_factor = 1 + (stock_dividend / Decimal('10'))
            ex_dividend_ref_price = (close_before - cash_dividend) / stock_dividend_factor
            
            # 計算還原權值因子
            # adjustment_factor = 除權息前收盤價 / 除權息參考價
            if ex_dividen_resultsd_ref_price != 0:
                adjustment_factor = close_before / ex_dividend_ref_price
            else:
                adjustment_factor = Decimal('1')
            
            # 更新 dividend 記錄
            dividends.update_one(
                {'_id': dividend['_id']},
                {'$set': {
                    'exDividendReferencePrice': Decimal128(ex_dividend_ref_price),
                    'adjustmentFactor': Decimal128(adjustment_factor),
                    'priceBeforeExDividend': Decimal128(close_before),
                    'priceAfterExDividend': Decimal128(close_after),
                    'updated_at': datetime.now()
                }}
            )
            
            updated_count += 1
            
            if updated_count % 100 == 0:
                logger.info(f"已處理 {updated_count} 筆...")
            
        except Exception as e:
            error_count += 1
            logger.error(f"處理失敗: {symbol} {ex_dividend_date} - {e}")
    
    logger.info(f"\n✅ 還原權值因子計算完成")
    logger.info(f"   更新筆數: {updated_count}")
    logger.info(f"   錯誤筆數: {error_count}")
    
    client.close()
    return True


def calculate_cumulative_factors():
    """
    計算累積還原權值因子
    
    從最新日期往回推，累乘所有的還原權值因子
    """
    logger.info("\n" + "="*80)
    logger.info("🔄 計算累積還原權值因子")
    prices = db.stock_price
    dividends = db.dividend_results
    
    # 獲取所有股票代碼
    symbols = prices.distinct('symbol')
    tickers = db.tickers
    dividends = db.dividends
    
    # 獲取所有股票代碼
    symbols = tickers.distinct('stock_id')
    logger.info(f"處理 {len(symbols)} 檔股票")
    
    processed_count = 0
    
    for symbol in symbols:
        try:
            # 獲取該股票的所有除權息資料（按日期排序）
            stock_dividends = list(dividends.find(
                {'stock_id': symbol},
                sort=[('date', 1)]
            ))
            
            if not stock_dividends:
                continue
            
            # 計算累積因子（從最早開始往後累乘）
            cumulative_factor = Decimal('1')
            
            for dividend in stock_dividends:
                adjustment_factor = extract_decimal(dividend.get('adjustmentFactor', 1))
                cumulative_factor *= adjustment_factor
                
                # 更新累積因子
                dividends.update_one(
                    {'_id': dividend['_id']},
                    {'$set': {
                        'cumulativeAdjustmentFactor': Decimal128(cumulative_factor)
                    }}
                )
            
            # 將最新的累積因子應用到 stock_price 集合
            # 這樣可以快速取得每個交易日應該使用的因子
            if stock_dividends:
                latest_cumulative = cumulative_factor
                
                # 為該股票的所有交易日設定累積因子
                prices.update_many(
                    {'symbol': symbol},
                    {'$set': {
                        'latestCumulativeAdjustmentFactor': Decimal128(latest_cumulative)
                    }}
                )
            
            processed_count += 1
            
            if processed_count % 100 == 0:
                logger.info(f"已處理 {processed_count}/{len(symbols)} 檔股票...")
            
        except Exception as e:
            logger.error(f"處理 {symbol} 失敗: {e}")
    
    logger.info(f"\n✅ 累積因子計算完成")
    logger.info(f"   處理股票數: {processed_count}")
    
    client.close()
    return True


def extract_decimal(value):
    """提取 Decimal 值"""
    if value is None:
        return Decimal('0')
    try:
        if isinstance(value, Decimal128):
            return value.to_decimal()
        elif isinstance(value, Decimal):
            return value
        elif isinstance(value, (int, float)):
            return Decimal(str(value))
        elif isinstance(value, str):
            return Decimal(value.replace(',', ''))
        return Decimal('0')
    except:
        return Decimal('0')


def main():
    """主程式"""
    logger.info("\n" + "="*80)
    logger.info("📊 還原權值計算工具")
    logger.info("="*80)
    logger.info(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80 + "\n")
    
    # 步驟 1: 計算基本還原權值因子
    logger.info("步驟 1: 計算還原權值因子...")
    result1 = calculate_adjustment_factors()
    
    if not result1:
        logger.error("❌ 還原權值因子計算失敗")
        return 1
    
    # 步驟 2: 計算累積因子
    logger.info("\n步驟 2: 計算累積還原權值因子...")
    result2 = calculate_cumulative_factors()
    
    if not result2:
        logger.error("❌ 累積因子計算失敗")
        return 1
    
    logger.info("\n" + "="*80)
    logger.info("✅ 所有計算完成")
    logger.info("="*80)
    logger.info("\n使用方式:")
    logger.info("  1. 計算還原股價: adjusted_price = price * cumulativeAdjustmentFactor")
    logger.info("  2. 用還原股價計算技術指標（MA, MACD, RSI 等）")
    logger.info("="*80 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
