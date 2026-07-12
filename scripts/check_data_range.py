#!/usr/bin/env python3
"""快速檢查數據範圍"""
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["tw_stock_analysis"]

# 價格資料範圍
price_min = db.stock_price.find_one({}, {'date': 1}, sort=[('date', 1)])
price_max = db.stock_price.find_one({}, {'date': 1}, sort=[('date', -1)])

print("價格資料範圍:")
print(f"  最早: {price_min['date']}")
print(f"  最晚: {price_max['date']}")
print(f"  總數: {db.stock_price.count_documents({})}")

# 股利資料統計
div_total = db.dividend_detail.count_documents({'CashEarningsDistribution': {'$gt': 0}})
div_2020 = db.dividend_detail.count_documents({
    'CashEarningsDistribution': {'$gt': 0},
    'CashExDividendTradingDate': {'$gte': '2020-01-01'}
})

print(f"\n股利資料:")
print(f"  總數(現金>0): {div_total}")
print(f"  2020後: {div_2020}")
print(f"  成功處理: {db.dividend_results.count_documents({})}")

client.close()
