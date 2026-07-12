#!/usr/bin/env python3
"""
檢查財報數據覆蓋率
"""

from pymongo import MongoClient

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 總股票數
    total_stocks = db.taiwan_stock_info.count_documents({})
    
    # 財報覆蓋率
    balance_stocks = len(db['TaiwanStockBalanceSheet'].distinct('stock_id'))
    balance_records = db['TaiwanStockBalanceSheet'].count_documents({})
    balance_coverage = (balance_stocks / total_stocks * 100) if total_stocks > 0 else 0
    
    income_stocks = len(db['TaiwanStockFinancialStatements'].distinct('stock_id'))
    income_records = db['TaiwanStockFinancialStatements'].count_documents({})
    income_coverage = (income_stocks / total_stocks * 100) if total_stocks > 0 else 0
    
    cashflow_stocks = len(db['TaiwanStockCashFlowsStatement'].distinct('stock_id'))
    cashflow_records = db['TaiwanStockCashFlowsStatement'].count_documents({})
    cashflow_coverage = (cashflow_stocks / total_stocks * 100) if total_stocks > 0 else 0
    
    # 台積電範例
    tsmc_income = db['TaiwanStockFinancialStatements'].count_documents({'stock_id': '2330'})
    latest_report = db['TaiwanStockFinancialStatements'].find_one(
        {'stock_id': '2330'}, 
        sort=[('date', -1)]
    )
    
    print("=" * 70)
    print("財報數據覆蓋率統計")
    print("=" * 70)
    print()
    print(f"總股票數: {total_stocks:,} 支")
    print()
    print("-" * 70)
    print()
    print("資產負債表 (TaiwanStockBalanceSheet):")
    print(f"   覆蓋股票數: {balance_stocks} / {total_stocks} 支")
    print(f"   覆蓋率: {balance_coverage:.2f}%")
    print(f"   總資料筆數: {balance_records:,} 筆")
    print()
    print("損益表 (TaiwanStockFinancialStatements):")
    print(f"   覆蓋股票數: {income_stocks} / {total_stocks} 支")
    print(f"   覆蓋率: {income_coverage:.2f}%")
    print(f"   總資料筆數: {income_records:,} 筆")
    print()
    print("現金流量表 (TaiwanStockCashFlowsStatement):")
    print(f"   覆蓋股票數: {cashflow_stocks} / {total_stocks} 支")
    print(f"   覆蓋率: {cashflow_coverage:.2f}%")
    print(f"   總資料筆數: {cashflow_records:,} 筆")
    print()
    print("-" * 70)
    print()
    print("範例：台積電 (2330)")
    print(f"   損益表資料筆數: {tsmc_income} 筆")
    if latest_report:
        print(f"   最新財報日期: {latest_report['date'].strftime('%Y-%m-%d')}")
    print()
    print("=" * 70)
    print()
    
    # 結論
    print("結論：")
    print()
    if income_coverage < 50:
        print("X 財報數據尚未完整覆蓋所有公司")
        print(f"   目前覆蓋率僅 {income_coverage:.2f}%")
        print(f"   約有 {total_stocks - income_stocks} 支股票缺少財報")
        print()
        print("建議：")
        print("   1. 執行完整財報下載")
        print("   2. 預估需要時間：視 FinMind API 配額而定")
        print(f"   3. 剩餘待下載：約 {total_stocks - income_stocks} 支股票")
    else:
        print(f"已覆蓋大部分公司 ({income_coverage:.2f}%)")

if __name__ == '__main__':
    main()
