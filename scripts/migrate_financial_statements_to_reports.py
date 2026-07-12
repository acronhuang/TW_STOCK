#!/usr/bin/env python3
"""
將 financial_statements 遷移到 financial_reports
確保負債資料正確
"""

from pymongo import MongoClient
from datetime import datetime

def migrate(symbols=None):
    """遷移財報數據"""
    print(f"\n{'='*80}")
    print(f"遷移 financial_statements → financial_reports")
    print(f"{'='*80}")
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 如果沒指定股票，則處理所有有資料的股票
    if symbols is None:
        query = {'source': 'finmind'}
    else:
        query = {'source': 'finmind', 'symbol': {'$in': symbols}}
    
    # 獲取所有 financial_statements
    statements = list(db.financial_statements.find(query).sort([('year', -1), ('season', -1)]))
    
    print(f"\n找到 {len(statements)} 筆財報")
    
    migrated_count = 0
    updated_count = 0
    
    for stmt in statements:
        symbol = stmt.get('symbol')
        year = stmt.get('fiscalYear') or stmt.get('year')
        period = stmt.get('fiscalPeriod') or f"Q{stmt.get('season')}"
        
        # 檢查是否有負債資料
        balance_sheet = stmt.get('balanceSheet', {})
        total_liabilities = balance_sheet.get('totalLiabilities', 0)
        
        print(f"\n{symbol} {year} {period} - 負債: {total_liabilities:,.0f}")
        
        # 更新到 financial_reports（不包含 dataSource 在查詢條件中）
        result = db.financial_reports.update_one(
            {
                'symbol': symbol,
                'fiscalYear': year,
                'fiscalPeriod': period
            },
            {
                '$set': {
                    'symbol': symbol,
                    'fiscalYear': year,
                    'fiscalPeriod': period,
                    'companyName': stmt.get('companyName', ''),
                    'dataSource': 'FinMind',
                    'incomeStatement': stmt.get('incomeStatement', {}),
                    'balanceSheet': balance_sheet,  # 包含 totalLiabilities
                    'cashflowStatement': stmt.get('cashflowStatement', {}),
                    'ratios': stmt.get('ratios', {}),
                    'updatedAt': datetime.now()
                }
            },
            upsert=True
        )
        
        if result.upserted_id:
            migrated_count += 1
        elif result.modified_count > 0:
            updated_count += 1
    
    print(f"\n{'='*80}")
    print(f"✅ 完成！新增 {migrated_count} 筆，更新 {updated_count} 筆")
    print(f"{'='*80}")

if __name__ == '__main__':
    import sys
    
    # 支援批次處理多支股票
    if len(sys.argv) > 1:
        symbols = sys.argv[1:]
        migrate(symbols)
    else:
        # 預設處理所有股票
        migrate()

