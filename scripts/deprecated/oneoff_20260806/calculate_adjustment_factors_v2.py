#!/usr/bin/env python3
"""
還原權值計算工具 v2
根據 dividend_results 計算還原權值因子
"""

import sys
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def to_decimal(value):
    """轉換為 Decimal"""
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

def calculate_adjustment_factors():
    """計算還原權值因子"""
    log("="*80)
    log("🔄 計算還原權值因子")
    log("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    if 'dividend_results' not in db.list_collection_names():
        log("❌ 找不到 dividend_results 集合")
        client.close()
        return False
    
    dividends = db.dividend_results
    total = dividends.count_documents({})
    log(f"📊 總股利記錄: {total}")
    
    if total == 0:
        log("⚠️  沒有股利資料")
        client.close()
        return False
    
    updated = 0
    skipped = 0
    errors = 0
    
    for div in dividends.find({}):
        try:
            # dividend_results 欄位:
            # - stock_id: 股票代碼
            # - date: 日期 (YYYY-MM-DD)
            # - stock_and_cache_dividend: 股利金額
            # - stock_or_cache_dividend: '息' 或 '權'
            # - reference_price: 除權息參考價
            # - before_price: 除權息前收盤價
            # - after_price: 除權息後收盤價
            
            amount = to_decimal(div.get('stock_and_cache_dividend', 0))
            ref_price = to_decimal(div.get('reference_price', 0))
            before = to_decimal(div.get('before_price', 0))
            
            if amount == 0 or before == 0:
                skipped += 1
                continue
            
            # 計算還原權值因子
            if ref_price > 0:
                # 使用交易所提供的參考價
                factor = before / ref_price
            else:
                # 無參考價，使用預設值
                factor = Decimal('1')
            
            # 更新記錄
            dividends.update_one(
                {'_id': div['_id']},
                {'$set': {
                    'adjustmentFactor': Decimal128(factor),
                    'updated_at': datetime.now()
                }}
            )
            
            updated += 1
            
            if updated % 100 == 0:
                log(f"   已處理: {updated}/{total}")
        
        except Exception as e:
            errors += 1
            if errors <= 5:
                log(f"   ⚠️  錯誤: {e}")
    
    log("")
    log("✅ 計算完成")
    log(f"   更新: {updated}")
    log(f"   跳過: {skipped}")
    log(f"   錯誤: {errors}")
    
    client.close()
    return True

def calculate_cumulative_factors():
    """計算累積還原權值因子"""
    log("")
    log("="*80)
    log("🔄 計算累積還原權值因子")
    log("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    dividends = db.dividend_results
    prices = db.stock_price
    
    # 取得所有股票
    symbols = dividends.distinct('stock_id')
    log(f"📊 處理 {len(symbols)} 檔股票")
    
    processed = 0
    
    for symbol in symbols:
        try:
            # 取得該股票的所有除權息記錄（按日期排序）
            divs = list(dividends.find(
                {'stock_id': symbol},
                sort=[('date', 1)]
            ))
            
            if not divs:
                continue
            
            # 計算累積因子（從最早往後累乘）
            cumulative = Decimal('1')
            
            for div in divs:
                factor = to_decimal(div.get('adjustmentFactor', 1))
                cumulative *= factor
                
                # 更新累積因子
                dividends.update_one(
                    {'_id': div['_id']},
                    {'$set': {
                        'cumulativeAdjustmentFactor': Decimal128(cumulative)
                    }}
                )
            
            # 將最新累積因子寫入 stock_price
            if cumulative != Decimal('1'):
                prices.update_many(
                    {'symbol': symbol},
                    {'$set': {
                        'latestCumulativeAdjustmentFactor': Decimal128(cumulative)
                    }}
                )
            
            processed += 1
            
            if processed % 100 == 0:
                log(f"   已處理: {processed}/{len(symbols)}")
        
        except Exception as e:
            log(f"   ⚠️  {symbol}: {e}")
    
    log("")
    log("✅ 累積因子計算完成")
    log(f"   處理股票數: {processed}")
    
    client.close()
    return True

def main():
    log("")
    log("="*80)
    log("📊 還原權值計算工具")
    log("="*80)
    log(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*80)
    log("")
    
    # 步驟 1: 計算基本因子
    r1 = calculate_adjustment_factors()
    if not r1:
        log("❌ 基本因子計算失敗")
        return 1
    
    # 步驟 2: 計算累積因子
    r2 = calculate_cumulative_factors()
    if not r2:
        log("❌ 累積因子計算失敗")
        return 1
    
    log("")
    log("="*80)
    log("🎉 所有計算完成")
    log("="*80)
    log("")
    log("使用方式:")
    log("  adjusted_price = price * cumulativeAdjustmentFactor")
    log("  用還原股價計算技術指標 (MA, MACD, RSI 等)")
    log("="*80)
    log("")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
