#!/usr/bin/env python3
"""
更新 financial_reports 和 financial_statements 的公司名稱
"""

from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print("="*60)
print("更新 financial_reports 的公司名稱")
print("="*60)

# 獲取所有有公司名稱的股票
stocks_with_names = {
    doc['symbol']: doc['name'] 
    for doc in db.stocks.find({'name': {'$exists': True, '$ne': ''}})
}

print(f"\n找到 {len(stocks_with_names)} 支股票有名稱")

# 更新 financial_reports
updated_reports = 0
for symbol, name in stocks_with_names.items():
    result = db.financial_reports.update_many(
        {'symbol': symbol},
        {'$set': {'companyName': name}}
    )
    if result.modified_count > 0:
        updated_reports += result.modified_count
        if updated_reports <= 50:
            print(f"  ✓ {symbol} {name}: 更新 {result.modified_count} 筆")

print(f"\n更新 financial_reports: {updated_reports} 筆")

# 更新 financial_statements
print(f"\n{'='*60}")
print("更新 financial_statements 的公司名稱")
print(f"{'='*60}\n")

updated_statements = 0
for symbol, name in stocks_with_names.items():
    result = db.financial_statements.update_many(
        {'symbol': symbol},
        {'$set': {'companyName': name}}
    )
    if result.modified_count > 0:
        updated_statements += result.modified_count

print(f"更新 financial_statements: {updated_statements} 筆")

# 驗證
print(f"\n{'='*60}")
print("驗證結果")
print(f"{'='*60}\n")

test_symbols = ['2330', '2317', '2454', '1101', '1216', '1301']
for symbol in test_symbols:
    stock = db.stocks.find_one({'symbol': symbol})
    report = db.financial_reports.find_one({'symbol': symbol, 'fiscalYear': 2024, 'fiscalPeriod': 'Q3'})
    
    stock_name = stock['name'] if stock else 'N/A'
    report_name = report['companyName'] if report and 'companyName' in report else 'N/A'
    
    status = '✓' if stock_name == report_name else '✗'
    print(f"{status} {symbol}: stocks={stock_name}, reports={report_name}")

print(f"\n{'='*60}")
print("完成")
print(f"{'='*60}")
