#!/usr/bin/env python3
"""
stock_price 集合 Decimal128 遷移腳本

將 stock_price 集合中的所有數值欄位從 float 轉換為 Decimal128
預估處理時間: 3-5 分鐘（500萬筆資料）
"""

import sys
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from decimal import Decimal, InvalidOperation

# 加入專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 不使用 logging，直接用 print 以提高效能
def log(message):
    """簡單的日誌輸出"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)


def migrate_stock_price_to_decimal128():
    """
    遷移 stock_price 集合到 Decimal128
    
    轉換欄位:
    - close: float → Decimal128
    - high: float → Decimal128
    - low: float → Decimal128
    - open: float → Decimal128
    - volume: float → Decimal128
    """
    log("="*80)
    log("🔄 開始遷移 stock_price 集合到 Decimal128")
    log("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    collection = db.stock_price
    
    # 統計總數
    total_count = collection.count_documents({})
    log(f"📊 總記錄數: {total_count:,}")
    
    if total_count == 0:
        log("⚠️  集合為空，無需遷移")
        client.close()
        return 0
    
    # 檢查是否已經是 Decimal128
    sample = collection.find_one({})
    if sample and isinstance(sample.get('close'), Decimal128):
        log("✅ 資料已經是 Decimal128 格式，無需遷移")
        client.close()
        return 0
    
    log(f"🎯 開始批次處理...")
    log(f"   批次大小: 10,000 筆")
    log(f"   預估時間: {total_count / 10000 * 0.5:.1f} - {total_count / 10000 * 1:.1f} 分鐘")
    log("")
    
    # 批次處理
    batch_size = 10000
    updated_count = 0
    error_count = 0
    skipped_count = 0
    
    # 使用 cursor 遍歷所有文檔
    cursor = collection.find({}, no_cursor_timeout=True).batch_size(batch_size)
    
    try:
        batch = []
        for doc in cursor:
            try:
                # 提取數值
                close = doc.get('close')
                high = doc.get('high')
                low = doc.get('low')
                open_price = doc.get('open')
                volume = doc.get('volume')
                
                # 檢查是否需要轉換
                needs_update = False
                update_fields = {}
                
                if close is not None and not isinstance(close, Decimal128):
                    try:
                        update_fields['close'] = Decimal128(Decimal(str(close)))
                        needs_update = True
                    except (InvalidOperation, ValueError):
                        pass
                
                if high is not None and not isinstance(high, Decimal128):
                    try:
                        update_fields['high'] = Decimal128(Decimal(str(high)))
                        needs_update = True
                    except (InvalidOperation, ValueError):
                        pass
                
                if low is not None and not isinstance(low, Decimal128):
                    try:
                        update_fields['low'] = Decimal128(Decimal(str(low)))
                        needs_update = True
                    except (InvalidOperation, ValueError):
                        pass
                
                if open_price is not None and not isinstance(open_price, Decimal128):
                    try:
                        update_fields['open'] = Decimal128(Decimal(str(open_price)))
                        needs_update = True
                    except (InvalidOperation, ValueError):
                        pass
                
                if volume is not None and not isinstance(volume, Decimal128):
                    try:
                        update_fields['volume'] = Decimal128(Decimal(str(volume)))
                        needs_update = True
                    except (InvalidOperation, ValueError):
                        pass
                
                if needs_update:
                    batch.append({
                        '_id': doc['_id'],
                        'update': update_fields
                    })
                else:
                    skipped_count += 1
                
                # 當批次達到大小時執行更新
                if len(batch) >= batch_size:
                    # 批次更新
                    for item in batch:
                        try:
                            collection.update_one(
                                {'_id': item['_id']},
                                {'$set': item['update']}
                            )
                            updated_count += 1
                        except Exception as e:
                            error_count += 1
                    
                    # 輸出進度
                    progress = (updated_count + skipped_count + error_count) / total_count * 100
                    log(f"   進度: {updated_count:,}/{total_count:,} ({progress:.1f}%) | 錯誤: {error_count}")
                    
                    batch = []
            
            except Exception as e:
                error_count += 1
                if error_count <= 10:  # 只顯示前10個錯誤
                    log(f"   ⚠️  處理失敗: {e}")
        
        # 處理剩餘的批次
        if batch:
            for item in batch:
                try:
                    collection.update_one(
                        {'_id': item['_id']},
                        {'$set': item['update']}
                    )
                    updated_count += 1
                except Exception as e:
                    error_count += 1
            
            progress = (updated_count + skipped_count + error_count) / total_count * 100
            log(f"   進度: {updated_count:,}/{total_count:,} ({progress:.1f}%) | 錯誤: {error_count}")
    
    finally:
        cursor.close()
    
    log("")
    log("="*80)
    log("✅ 遷移完成")
    log("="*80)
    log(f"   總記錄數: {total_count:,}")
    log(f"   已更新: {updated_count:,}")
    log(f"   已跳過: {skipped_count:,}")
    log(f"   錯誤: {error_count}")
    log("="*80)
    
    client.close()
    
    return 0 if error_count == 0 else 1


def verify_migration():
    """驗證遷移結果"""
    log("")
    log("🔍 驗證遷移結果...")
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    collection = db.stock_price
    
    # 抽樣檢查
    sample_size = 1000
    samples = list(collection.find({}).limit(sample_size))
    
    decimal128_count = 0
    float_count = 0
    
    for doc in samples:
        if isinstance(doc.get('close'), Decimal128):
            decimal128_count += 1
        else:
            float_count += 1
    
    log(f"   抽樣檢查: {sample_size} 筆")
    log(f"   ✅ Decimal128: {decimal128_count} ({decimal128_count/sample_size*100:.1f}%)")
    log(f"   ❌ Float: {float_count} ({float_count/sample_size*100:.1f}%)")
    
    if float_count == 0:
        log("   ✅ 驗證通過：所有欄位已轉換為 Decimal128")
        result = True
    else:
        log("   ⚠️  驗證失敗：仍有欄位為 float")
        result = False
    
    client.close()
    return result


def main():
    """主程式"""
    log("")
    log("="*80)
    log("📊 stock_price 集合 Decimal128 遷移工具")
    log("="*80)
    log(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*80)
    log("")
    
    # 執行遷移
    result = migrate_stock_price_to_decimal128()
    
    if result != 0:
        log("")
        log("❌ 遷移失敗")
        return 1
    
    # 驗證結果
    verify_result = verify_migration()
    
    if not verify_result:
        log("")
        log("❌ 驗證失敗")
        return 1
    
    log("")
    log("="*80)
    log("🎉 所有作業完成")
    log("="*80)
    log("")
    log("下一步:")
    log("  1. 重新下載股利資料: python3 scripts/main_download.py")
    log("  2. 計算還原權值: python3 scripts/calculate_adjustment_factors.py")
    log("="*80)
    log("")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
