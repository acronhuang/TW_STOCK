#!/usr/bin/env python3
"""
測試因子計算
"""
from pymongo import MongoClient
from datetime import datetime
import sys
from pathlib import Path

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.factors.value_factors import ValueFactors
from src.factors.quality_factors import QualityFactors

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 測試日期
test_date = datetime(2024, 12, 31)

print("=" * 80)
print("測試因子計算 - 2330 台積電")
print("=" * 80)

# 價值因子
print("\n【價值因子】")
value_factors = ValueFactors(db)

pe = value_factors.calculate_pe_ratio('2330', test_date)
print(f"PE Ratio: {pe:.2f}" if pe else "PE Ratio: None")

pb = value_factors.calculate_pb_ratio('2330', test_date)
print(f"PB Ratio: {pb:.2f}" if pb else "PB Ratio: None")

# 質量因子
print("\n【質量因子】")
quality_factors = QualityFactors(db)

roe = quality_factors.calculate_roe('2330', test_date)
print(f"ROE: {roe:.2f}%" if roe else "ROE: None")

roa = quality_factors.calculate_roa('2330', test_date)
print(f"ROA: {roa:.2f}%" if roa else "ROA: None")

# 檢查數據源
print("\n【數據源檢查】")

# 股價
price = db.stock_price.find_one({'symbol': '2330', 'date': test_date})
if price:
    from bson.decimal128 import Decimal128
    close_val = price['close']
    if isinstance(close_val, Decimal128):
        close_val = float(close_val.to_decimal())
    print(f"Stock Price: ${close_val:.2f}")
else:
    print("Stock Price: None")

# 財報（排除無效數據）
financial = db.financial_reports.find_one(
    {'symbol': '2330', 'incomeStatement.netIncome': {'$gt': 0}},
    sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
)
if financial:
    print(f"Latest Financial Report: {financial.get('fiscalYear')} {financial.get('fiscalPeriod')}")
    if 'incomeStatement' in financial:
        net_income = financial['incomeStatement'].get('netIncome')
        if net_income:
            from bson.decimal128 import Decimal128
            if isinstance(net_income, Decimal128):
                net_income = float(net_income.to_decimal())
            print(f"  Net Income: {net_income:,.0f}")
        else:
            print("  Net Income: None")
    if 'balanceSheet' in financial:
        equity = financial['balanceSheet'].get('equity')
        total_assets = financial['balanceSheet'].get('totalAssets')
        if equity:
            from bson.decimal128 import Decimal128
            if isinstance(equity, Decimal128):
                equity = float(equity.to_decimal())
            print(f"  Equity: {equity:,.0f}")
        else:
            print("  Equity: None")
        if total_assets:
            from bson.decimal128 import Decimal128
            if isinstance(total_assets, Decimal128):
                total_assets = float(total_assets.to_decimal())
            print(f"  Total Assets: {total_assets:,.0f}")
        else:
            print("  Total Assets: None")
else:
    print("Latest Financial Report: None")

# 股票資訊
stock_info = db.taiwan_stock_info.find_one({'stock_id': '2330'}, sort=[('date', -1)])
if stock_info:
    from bson.decimal128 import Decimal128
    shares = stock_info['outstanding_shares']
    if isinstance(shares, Decimal128):
        shares = float(shares.to_decimal())
    print(f"Outstanding Shares: {shares:,.2f} (千股)")
else:
    print("Outstanding Shares: None")

client.close()

print("\n" + "=" * 80)
