#!/usr/bin/env python3
"""測試新的 value_factors.py (使用 TaiwanStockPER)"""
import sys
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.factors.value_factors import ValueFactors

# 連接 MongoDB
db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
calculator = ValueFactors(db)

# 測試 2330
test_date = datetime(2024, 2, 20)

print('=' * 60)
print(f'測試新的 value_factors.py (TaiwanStockPER)')
print('=' * 60)
print(f'\n測試股票: 2330')
print(f'測試日期: {test_date.strftime("%Y-%m-%d")}')

# 檢查是否有 PE/PB 數據
per_doc = db.taiwan_stock_per.find_one({'stock_id': '2330', 'date': test_date})
if per_doc:
    print(f'\n✓ taiwan_stock_per 有數據')
    print(f'  PER: {per_doc.get("PER")}')
    print(f'  PBR: {per_doc.get("PBR")}')
else:
    print(f'\n❌ taiwan_stock_per 沒有數據')

# 測試新方法
print(f'\n計算結果:')
pe = calculator.calculate_pe_ratio('2330', test_date)
pb = calculator.calculate_pb_ratio('2330', test_date)

if pe:
    print(f'✅ PE Ratio: {pe:.2f}')
else:
    print(f'❌ PE Ratio: None')

if pb:
    print(f'✅ PB Ratio: {pb:.2f}')
else:
    print(f'❌ PB Ratio: None')

print('\n' + '=' * 60)

if pe and pb:
    print('✅ 新方法工作正常！')
else:
    print('⚠️  新方法返回 None，請檢查')
