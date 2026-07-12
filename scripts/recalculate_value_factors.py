#!/usr/bin/env python3
"""
重新計算價值因子 (使用新的 TaiwanStockPER 數據)
"""
import sys
from pathlib import Path
from datetime import datetime
import time
from pymongo import MongoClient

# 設定專案路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.factors.factor_calculator import FactorCalculator

def main():
    print('=' * 60)
    print('重新計算價值因子 (使用 TaiwanStockPER)')
    print('=' * 60)
    
    # 連接 MongoDB
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 初始化因子計算器
    calculator = FactorCalculator(db_name='tw_stock_analysis')
    
    # 統計
    有PER股票 = list(db.taiwan_stock_per.distinct('stock_id'))
    print(f'\n有 PE/PB 數據的股票: {len(有PER股票)}')
    
    # 取得這些股票的所有交易日
    print(f'正在統計交易記錄...')
    total_records = db.stock_price.count_documents({
        'symbol': {'$in': 有PER股票}
    })
    print(f'需要計算的記錄數: {total_records:,}\n')
    
    # 統計現有因子
    existing = db.stock_factors.count_documents({
        'symbol': {'$in': 有PER股票},
        'pe_ratio': {'$exists': True, '$ne': None}
    })
    print(f'現有 PE 因子記錄: {existing:,}')
    print(f'覆蓋率: {existing/total_records*100:.1f}%\n')
    
    # 詢問確認
    print('這將重新計算所有價值因子（PE, PB）')
    print('是否繼續？ (輸入 YES 確認)')
    confirm = input('> ')
    
    if confirm != 'YES':
        print('\n已取消')
        return
    
    print('\n開始計算...\n')
    start_time = time.time()
    
    # 批次處理
    processed = 0
    updated = 0
    errors = 0
    batch_size = 100
    
    # 取得所有需要計算的記錄
    cursor = db.stock_price.find(
        {'symbol': {'$in': 有PER股票}},
        {'symbol': 1, 'date': 1}
    ).sort('symbol', 1)
    
    batch = []
    for record in cursor:
        batch.append((record['symbol'], record['date']))
        
        if len(batch) >= batch_size:
            # 處理批次
            for symbol, date in batch:
                try:
                    factors = calculator.calculate_factors(symbol, date)
                    
                    if factors:
                        # 更新因子
                        result = db.stock_factors.update_one(
                            {'symbol': symbol, 'date': date},
                            {'$set': {
                                'pe_ratio': factors.get('pe_ratio'),
                                'pb_ratio': factors.get('pb_ratio'),
                                'updated_at': datetime.now()
                            }},
                            upsert=True
                        )
                        
                        if result.modified_count > 0 or result.upserted_id:
                            updated += 1
                    
                    processed += 1
                    
                    if processed % 1000 == 0:
                        elapsed = time.time() - start_time
                        speed = processed / elapsed
                        remaining = (total_records - processed) / speed if speed > 0 else 0
                        print(f'  進度: {processed:>7,}/{total_records:,} ({processed/total_records*100:>5.1f}%) '
                              f'| 更新: {updated:>6,} | {speed:>5.0f} 筆/秒 | 剩餘: {remaining/60:>4.1f} 分')
                
                except Exception as e:
                    errors += 1
                    if errors <= 10:
                        print(f'  錯誤: {symbol} {date}: {str(e)}')
            
            batch = []
    
    # 處理剩餘的記錄
    for symbol, date in batch:
        try:
            factors = calculator.calculate_factors(symbol, date)
            
            if factors:
                result = db.stock_factors.update_one(
                    {'symbol': symbol, 'date': date},
                    {'$set': {
                        'pe_ratio': factors.get('pe_ratio'),
                        'pb_ratio': factors.get('pb_ratio'),
                        'updated_at': datetime.now()
                    }},
                    upsert=True
                )
                
                if result.modified_count > 0 or result.upserted_id:
                    updated += 1
            
            processed += 1
        except Exception as e:
            errors += 1
    
    # 總結
    elapsed = time.time() - start_time
    
    print('\n' + '=' * 60)
    print('計算完成')
    print('=' * 60)
    print(f'處理記錄: {processed:,}')
    print(f'更新記錄: {updated:,}')
    print(f'錯誤:     {errors:,}')
    print(f'耗時:     {elapsed:.1f} 秒 ({elapsed/60:.1f} 分鐘)')
    print('=' * 60)
    
    # 驗證
    print('\n正在驗證結果...')
    new_total = db.stock_factors.count_documents({
        'symbol': {'$in': 有PER股票},
        'pe_ratio': {'$exists': True, '$ne': None}
    })
    print(f'現有 PE 因子: {new_total:,}')
    print(f'覆蓋率: {new_total/total_records*100:.1f}%')
    
    client.close()

if __name__ == '__main__':
    main()
