#!/usr/bin/env python3
"""
將 FinMind 財報數據轉換為 NestJS 可用的格式
"""

from pymongo import MongoClient
from datetime import datetime
from collections import defaultdict

def reorganize_financial_data(symbol='2330'):
    """重新組織財報數據"""
    print(f"\n{'='*80}")
    print(f"重新組織 {symbol} 財報數據")
    print(f"{'='*80}")
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 取得所有 2330 的財報
    reports = list(db.financial_statements.find(
        {'symbol': symbol, 'source': 'finmind'}
    ).sort([('year', -1), ('season', -1)]))
    
    print(f"\n找到 {len(reports)} 筆財報")
    
    updated_count = 0
    
    for report in reports:
        year = report.get('year')
        season = report.get('season')
        data = report.get('data', {})
        
        print(f"\n處理 {year}Q{season}...")
        
        # 提取資產負債表
        balance_sheet_data = {}
        bs_list = data.get('balance_sheet', [])
        if isinstance(bs_list, list):
            for item in bs_list:
                type_name = item.get('type', '')
                value = item.get('value', 0)
                balance_sheet_data[type_name] = value
        elif isinstance(bs_list, dict):
            # 已經是字典格式，取最後一筆
            type_name = bs_list.get('type', '')
            value = bs_list.get('value', 0)
            if type_name:
                balance_sheet_data[type_name] = value
        
        # 提取損益表
        income_statement_data = {}
        inc_list = data.get('income_statement', [])
        if isinstance(inc_list, list):
            for item in inc_list:
                type_name = item.get('type', '')
                value = item.get('value', 0)
                income_statement_data[type_name] = value
        elif isinstance(inc_list, dict):
            type_name = inc_list.get('type', '')
            value = inc_list.get('value', 0)
            if type_name:
                income_statement_data[type_name] = value
        
        # 提取現金流量表
        cashflow_data = {}
        cf_list = data.get('cashflow_statement', [])
        if isinstance(cf_list, list):
            for item in cf_list:
                type_name = item.get('type', '')
                value = item.get('value', 0)
                cashflow_data[type_name] = value
        elif isinstance(cf_list, dict):
            type_name = cf_list.get('type', '')
            value = cf_list.get('value', 0)
            if type_name:
                cashflow_data[type_name] = value
        
        # 映射關鍵欄位（杜邦分析需要）
        # 從損益表
        revenue = (
            income_statement_data.get('Revenue') or
            income_statement_data.get('OperatingRevenue') or
            income_statement_data.get('TotalOperatingRevenue') or
            0
        )
        
        gross_profit = (
            income_statement_data.get('GrossProfit') or
            income_statement_data.get('GrossProfitLoss') or
            0
        )
        
        operating_income = (
            income_statement_data.get('OperatingIncome') or
            income_statement_data.get('OperatingIncomeLoss') or
            income_statement_data.get('NetOperatingIncomeLoss') or
            0
        )
        
        net_income = (
            income_statement_data.get('ProfitLoss') or
            income_statement_data.get('NetIncome') or
            income_statement_data.get('IncomeFromContinuingOperations') or
            income_statement_data.get('ProfitLossAttributableToOwnersOfParent') or
            0
        )
        
        # 從資產負債表
        total_assets = (
            balance_sheet_data.get('TotalAssets') or
            balance_sheet_data.get('Assets') or
            0
        )
        
        total_equity = (
            balance_sheet_data.get('TotalEquity') or
            balance_sheet_data.get('Equity') or
            balance_sheet_data.get('EquityAttributableToOwnersOfParent') or
            0
        )
        
        # 計算負債（FinMind 沒有直接提供，需要計算）
        total_liabilities = total_assets - total_equity if (total_assets and total_equity) else 0
        
        # 計算比率
        gross_margin = (gross_profit / revenue * 100) if revenue else 0
        operating_margin = (operating_income / revenue * 100) if revenue else 0
        net_margin = (net_income / revenue * 100) if revenue else 0
        
        # 組織成 NestJS 期望的格式
        organized_data = {
            'symbol': symbol,
            'year': year,
            'season': season,
            'fiscalYear': year,
            'fiscalPeriod': f'Q{season}',
            'source': 'finmind',
            'dataSource': 'FinMind API',
            'companyName': '台積電',
            
            # 損益表
            'incomeStatement': {
                'revenue': revenue,
                'grossProfit': gross_profit,
                'operatingIncome': operating_income,
                'netIncome': net_income,
                'grossMargin': gross_margin,
                'operatingMargin': operating_margin,
                'netMargin': net_margin,
                '_raw': income_statement_data  # 保留原始數據
            },
            
            # 資產負債表
            'balanceSheet': {
                'totalAssets': total_assets,
                'equity': total_equity,
                'totalLiabilities': total_liabilities,  # 新增負債
                '_raw': balance_sheet_data
            },
            
            # 現金流量表
            'cashflowStatement': {
                '_raw': cashflow_data
            },
            
            # 財務比率（供杜邦分析）
            'ratios': {
                'roe': (net_income / total_equity * 100) if total_equity else 0,
                'roa': (net_income / total_assets * 100) if total_assets else 0,
                'grossMargin': gross_margin,
                'operatingMargin': operating_margin,
                'netMargin': net_margin
            },
            
            'updateTime': datetime.now(),
            'data': data  # 保留原始結構
        }
        
        # 更新資料庫
        result = db.financial_statements.update_one(
            {
                'symbol': symbol,
                'year': year,
                'season': season,
                'source': 'finmind'
            },
            {'$set': organized_data},
            upsert=True
        )
        
        if result.modified_count > 0 or result.upserted_id:
            updated_count += 1
            print(f"  ✅ 已更新 - 營收: {revenue:,.0f}, 淨利: {net_income:,.0f}, 總資產: {total_assets:,.0f}")
        else:
            print(f"  ⚠️  無變更")
    
    print(f"\n{'='*80}")
    print(f"✅ 完成！共更新 {updated_count} 筆財報")
    print(f"{'='*80}")
    
    return updated_count

if __name__ == '__main__':
    import sys
    
    # 支援批次處理多支股票
    if len(sys.argv) > 1:
        symbols = sys.argv[1:]
    else:
        # 預設處理所有有 FinMind 資料的股票
        client = MongoClient('mongodb://localhost:27017/')
        db = client['tw_stock_analysis']
        symbols = db.financial_statements.distinct('symbol', {'source': 'finmind'})
    
    print(f"\n{'='*80}")
    print(f"批次重組財報數據")
    print(f"股票清單: {', '.join(symbols)}")
    print(f"{'='*80}")
    
    total_updated = 0
    for symbol in symbols:
        try:
            count = reorganize_financial_data(symbol)
            total_updated += count
        except Exception as e:
            print(f"\n✗ {symbol} 處理失敗: {str(e)}")
            continue
    
    print(f"\n{'='*80}")
    print(f"✅ 批次處理完成！共處理 {len(symbols)} 支股票，更新 {total_updated} 筆財報")
    print(f"{'='*80}")

