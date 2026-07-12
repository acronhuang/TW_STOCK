#!/usr/bin/env python3
"""
清理异常价格数据
将 close <= 0 或逻辑矛盾的数据标记为无效
"""

import sys
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def clean_invalid_prices():
    """清理价格异常数据"""
    log("="*80)
    log("清理异常价格数据")
    log("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    collection = db.stock_price
    
    # 1. 标记 close <= 0 的记录
    log("\n1. 处理价格 <= 0 的记录...")
    result1 = collection.update_many(
        {'close': {'$lte': 0}},
        {'$set': {'isValid': False, 'invalidReason': 'price_lte_zero'}}
    )
    log(f"   标记为无效: {result1.modified_count} 笔")
    
    # 2. 可选：删除而非标记（谨慎使用）
    # delete_count = collection.delete_many({'close': {'$lte': 0}}).deleted_count
    # log(f"   删除: {delete_count} 笔")
    
    log("\n✅ 清理完成")
    log(f"   建议: 下次下载时，DataValidator 会自动过滤这类数据")
    
    client.close()
    return True

def verify_cleanup():
    """验证清理结果"""
    log("\n" + "="*80)
    log("验证清理结果")
    log("="*80)
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    total = db.stock_price.count_documents({})
    invalid_marked = db.stock_price.count_documents({'isValid': False})
    still_invalid = db.stock_price.count_documents({'close': {'$lte': 0}, 'isValid': {'$ne': False}})
    
    log(f"\n总记录数: {total:,}")
    log(f"已标记无效: {invalid_marked:,}")
    log(f"仍有未标记异常: {still_invalid:,}")
    
    if still_invalid == 0:
        log("\n✅ 所有异常数据已处理")
    else:
        log("\n⚠️ 仍有未处理的异常数据")
    
    client.close()

def main():
    log("\n" + "="*80)
    log("异常数据清理工具")
    log("="*80)
    log(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("="*80)
    
    # 清理
    clean_invalid_prices()
    
    # 验证
    verify_cleanup()
    
    log("\n" + "="*80)
    log("🎉 处理完成")
    log("="*80)
    log("\n说明:")
    log("  - 异常数据已标记为 isValid: false")
    log("  - 查询时可加上过滤: {isValid: {$ne: false}}")
    log("  - 或在 Schema 中建立 View 自动过滤")
    log("="*80 + "\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
