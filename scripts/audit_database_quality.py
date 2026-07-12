#!/usr/bin/env python3
"""
資料庫邏輯檢查腳本
執行專業級資料品質審計
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

from src.downloaders.data_validator import DataValidator

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/data_audit_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def extract_decimal(value):
    """提取 Decimal 值"""
    if value is None:
        return None
    try:
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        elif isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            return float(value.replace(',', ''))
    except:
        return None


def audit_price_logic():
    """審計價格邏輯"""
    logger.info("\n" + "="*80)
    logger.info("📊 審計 1: 價格邏輯檢查")
    logger.info("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 檢查 tickers 集合
    logger.info("\n檢查 tickers 集合...")
    tickers = db.tickers
    
    total_records = tickers.count_documents({})
    logger.info(f"總記錄數: {total_records:,}")
    
    if total_records == 0:
        logger.warning("⚠️  tickers 集合為空，跳過檢查")
        return
    
    # 抽樣檢查（前 1000 筆 + 隨機 1000 筆）
    sample_size = min(1000, total_records)
    logger.info(f"抽樣檢查: {sample_size} 筆")
    
    errors = []
    warnings = []
    
    for record in tickers.find().limit(sample_size):
        symbol = record.get('symbol')
        date = record.get('date')
        
        high = extract_decimal(record.get('highPrice') or record.get('high'))
        low = extract_decimal(record.get('lowPrice') or record.get('low'))
        close = extract_decimal(record.get('closePrice') or record.get('close'))
        open_price = extract_decimal(record.get('openPrice') or record.get('open'))
        volume = extract_decimal(record.get('tradeVolume') or record.get('volume'))
        
        # 檢查 1: 價格 > 0
        if high is not None and high <= 0:
            errors.append(f"最高價 <= 0: {symbol} [{date}] high={high}")
        if low is not None and low <= 0:
            errors.append(f"最低價 <= 0: {symbol} [{date}] low={low}")
        if close is not None and close <= 0:
            errors.append(f"收盤價 <= 0: {symbol} [{date}] close={close}")
        
        # 檢查 2: 價格邏輯關係
        if high and close and low:
            if high < close:
                errors.append(f"最高價 < 收盤價: {symbol} [{date}] high={high:.2f}, close={close:.2f}")
            if close < low:
                errors.append(f"收盤價 < 最低價: {symbol} [{date}] close={close:.2f}, low={low:.2f}")
            if high < low:
                errors.append(f"最高價 < 最低價: {symbol} [{date}] high={high:.2f}, low={low:.2f}")
        
        # 檢查 3: 開盤價範圍
        if open_price and high and low:
            if open_price > high * 1.01:  # 允許 1% 誤差
                warnings.append(f"開盤價 > 最高價: {symbol} [{date}] open={open_price:.2f}, high={high:.2f}")
            if open_price < low * 0.99:
                warnings.append(f"開盤價 < 最低價: {symbol} [{date}] open={open_price:.2f}, low={low:.2f}")
        
        # 檢查 4: 成交量
        if volume is not None and volume < 0:
            errors.append(f"成交量為負: {symbol} [{date}] volume={volume}")
    
    # 報告結果
    logger.info(f"\n📊 檢查結果:")
    logger.info(f"   檢查筆數: {sample_size:,}")
    logger.info(f"   錯誤數量: {len(errors)}")
    logger.info(f"   警告數量: {len(warnings)}")
    
    if errors:
        logger.error(f"\n❌ 發現 {len(errors)} 個邏輯錯誤:")
        for i, error in enumerate(errors[:10], 1):
            logger.error(f"   {i}. {error}")
        if len(errors) > 10:
            logger.error(f"   ... 還有 {len(errors) - 10} 個錯誤")
    else:
        logger.info("   ✅ 價格邏輯檢查通過")
    
    if warnings:
        logger.warning(f"\n⚠️  發現 {len(warnings)} 個警告:")
        for i, warning in enumerate(warnings[:10], 1):
            logger.warning(f"   {i}. {warning}")
        if len(warnings) > 10:
            logger.warning(f"   ... 還有 {len(warnings) - 10} 個警告")
    
    client.close()
    return len(errors) == 0


def audit_decimal_precision():
    """審計數值精確度"""
    logger.info("\n" + "="*80)
    logger.info("📊 審計 2: 數值精確度檢查")
    logger.info("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    collections_to_check = ['tickers', 'financial_reports', 'dividends']
    
    results = {}
    
    for coll_name in collections_to_check:
        if coll_name not in db.list_collection_names():
            logger.warning(f"⚠️  集合 {coll_name} 不存在，跳過")
            continue
        
        coll = db[coll_name]
        total = coll.count_documents({})
        
        if total == 0:
            logger.warning(f"⚠️  集合 {coll_name} 為空，跳過")
            continue
        
        logger.info(f"\n檢查集合: {coll_name} ({total:,} 筆)")
        
        # 抽樣檢查
        sample = coll.find_one()
        
        if not sample:
            continue
        
        # 檢查數值欄位型別
        numeric_fields = []
        decimal128_fields = []
        float_fields = []
        
        for key, value in sample.items():
            if isinstance(value, Decimal128):
                decimal128_fields.append(key)
            elif isinstance(value, (int, float)):
                if key in ['closePrice', 'highPrice', 'lowPrice', 'openPrice', 'price', 'amount', 'revenue']:
                    float_fields.append(key)
        
        logger.info(f"   Decimal128 欄位: {len(decimal128_fields)}")
        logger.info(f"   Float 欄位: {len(float_fields)}")
        
        if float_fields:
            logger.warning(f"   ⚠️  發現使用 Float 的金額欄位: {', '.join(float_fields)}")
            logger.warning(f"   建議: 將這些欄位遷移至 Decimal128")
        
        results[coll_name] = {
            'total': total,
            'decimal128_fields': len(decimal128_fields),
            'float_fields': len(float_fields),
            'needs_migration': len(float_fields) > 0
        }
    
    # 總結
    logger.info(f"\n📊 精確度審計總結:")
    all_good = True
    for coll_name, result in results.items():
        if result['needs_migration']:
            logger.warning(f"   ❌ {coll_name}: 需要遷移 {result['float_fields']} 個欄位")
            all_good = False
        else:
            logger.info(f"   ✅ {coll_name}: 全部使用 Decimal128")
    
    client.close()
    return all_good


def audit_missing_fields():
    """審計缺失欄位"""
    logger.info("\n" + "="*80)
    logger.info("📊 審計 3: 關鍵欄位缺失分析")
    logger.info("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 檢查 tickers 集合
    if 'tickers' in db.list_collection_names():
        tickers = db.tickers
        sample = tickers.find_one()
        
        if sample:
            logger.info("\n檢查 tickers 集合的欄位...")
            
            # 檢查還原權值相關欄位
            critical_fields = {
                'adjustmentFactor': '還原權值因子',
                'exDividendReferencePrice': '除權息參考價',
                'cumulativeAdjustmentFactor': '累積調整係數'
            }
            
            missing_fields = []
            for field, desc in critical_fields.items():
                if field not in sample:
                    missing_fields.append(f"{field} ({desc})")
            
            if missing_fields:
                logger.warning(f"\n❌ 缺少 P0 級關鍵欄位:")
                for field in missing_fields:
                    logger.warning(f"   • {field}")
                logger.warning(f"\n影響: 無法進行正確的技術分析（均線、MACD 等）")
                logger.warning(f"建議: 從股利資料計算或擴充資料來源")
            else:
                logger.info(f"   ✅ 還原權值欄位完整")
    
    # 檢查 dividends 集合
    if 'dividends' in db.list_collection_names():
        dividends = db.dividends
        sample = dividends.find_one()
        
        if sample:
            logger.info("\n檢查 dividends 集合的欄位...")
            
            important_fields = {
                'dividendPayoutDate': '股利發放日',
                'taxCreditRatio': '可扣抵稅率'
            }
            
            missing_fields = []
            for field, desc in important_fields.items():
                if field not in sample:
                    missing_fields.append(f"{field} ({desc})")
            
            if missing_fields:
                logger.warning(f"\n⚠️  缺少 P1 級重要欄位:")
                for field in missing_fields:
                    logger.warning(f"   • {field}")
            else:
                logger.info(f"   ✅ 股利欄位完整")
    
    client.close()


def main():
    """主程式"""
    logger.info("\n" + "="*80)
    logger.info("🔍 財經資料庫品質審計")
    logger.info("="*80)
    logger.info(f"審計時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80 + "\n")
    
    results = []
    
    # 審計 1: 價格邏輯
    try:
        result1 = audit_price_logic()
        results.append(("價格邏輯", result1))
    except Exception as e:
        logger.error(f"審計 1 失敗: {e}", exc_info=True)
        results.append(("價格邏輯", False))
    
    # 審計 2: 數值精確度
    try:
        result2 = audit_decimal_precision()
        results.append(("數值精確度", result2))
    except Exception as e:
        logger.error(f"審計 2 失敗: {e}", exc_info=True)
        results.append(("數值精確度", False))
    
    # 審計 3: 缺失欄位
    try:
        audit_missing_fields()
        results.append(("缺失欄位", None))  # 這個只是分析，不是通過/失敗
    except Exception as e:
        logger.error(f"審計 3 失敗: {e}", exc_info=True)
    
    # 總結
    logger.info("\n" + "="*80)
    logger.info("📊 審計總結")
    logger.info("="*80)
    
    for name, result in results:
        if result is None:
            logger.info(f"   📋 {name}: 已分析")
        elif result:
            logger.info(f"   ✅ {name}: 通過")
        else:
            logger.error(f"   ❌ {name}: 失敗")
    
    logger.info("\n" + "="*80)
    logger.info("✅ 審計完成")
    logger.info("="*80 + "\n")
    
    # 返回狀態碼
    failed_count = sum(1 for _, result in results if result is False)
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
