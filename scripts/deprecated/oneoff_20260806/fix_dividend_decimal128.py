#!/usr/bin/env python3
"""
修复 dividend_results 集合的字段精度问题
将价格和股利字段转换为 Decimal128
"""

from pymongo import MongoClient
from bson.decimal128 import Decimal128
from decimal import Decimal

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print('开始修复 dividend_results 集合的精度问题...\n')
    
    # 需要转换的字段
    fields_to_convert = [
        'stock_and_cache_dividend',  # 股票股利 + 现金股利
        'before_price',              # 除权息前价格
        'reference_price',           # 除权息参考价
        'adjustmentFactor',          # 还原权值因子
        'cumulativeAdjustmentFactor' # 累积还原权值因子
    ]
    
    # 检查需要转换的记录
    total = db.dividend_results.count_documents({})
    print(f'总记录数: {total}')
    
    # 逐笔转换
    updated = 0
    for doc in db.dividend_results.find({}):
        update_fields = {}
        
        for field in fields_to_convert:
            if field in doc:
                value = doc[field]
                # 如果不是 Decimal128，则转换
                if not isinstance(value, Decimal128):
                    if isinstance(value, (int, float)):
                        update_fields[field] = Decimal128(Decimal(str(value)))
                    elif isinstance(value, str):
                        update_fields[field] = Decimal128(Decimal(value))
        
        if update_fields:
            db.dividend_results.update_one(
                {'_id': doc['_id']},
                {'$set': update_fields}
            )
            updated += 1
    
    print(f'\n✅ 已更新 {updated} 笔记录')
    print('\n验证转换结果:')
    
    sample = db.dividend_results.find_one({})
    if sample:
        for field in fields_to_convert:
            if field in sample:
                value = sample[field]
                is_decimal = isinstance(value, Decimal128)
                status = '✅ Decimal128' if is_decimal else f'❌ {type(value).__name__}'
                print(f'  {field:35s}: {status}')
    
    client.close()
    print('\n🎉 修复完成！')

if __name__ == '__main__':
    main()
