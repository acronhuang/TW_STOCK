#!/usr/bin/env python3
"""檢查 adj_close 欄位的狀態"""

from pymongo import MongoClient
from bson import Decimal128

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 檢查 0050 的前10筆記錄
records = list(db.stock_price.find({'symbol': '0050'}).sort('date', 1).limit(10))

print('0050 前10筆記錄:')
for r in records:
    close = r.get('close')
    adj_close = r.get('adj_close')
    adj_factor = r.get('adjustment_factor')
    
    # 轉換 Decimal128 為 float
    if isinstance(close, Decimal128):
        close = float(close.to_decimal())
    if isinstance(adj_close, Decimal128):
        adj_close = float(adj_close.to_decimal())
    if isinstance(adj_factor, Decimal128):
        adj_factor = float(adj_factor.to_decimal())
    
    equal = "✅" if close == adj_close else "⚠️"
    print(f'{equal} {r["date"].strftime("%Y-%m-%d")}: close={close:.2f}, adj_close={adj_close:.2f}, factor={adj_factor:.6f}')

# 檢查0050有除息的日期
dividends = list(db.dividend_detail.find({'symbol': '0050'}).sort('ex_dividend_date', 1).limit(5))
print(f'\n0050 除息事件 (前5筆):')
for d in dividends:
    cash = d.get('cash_earnings_distribution', 0)
    if isinstance(cash, Decimal128):
        cash = float(cash.to_decimal())
    print(f'  {d["ex_dividend_date"].strftime("%Y-%m-%d")}: 現金股利 {cash:.2f}')
