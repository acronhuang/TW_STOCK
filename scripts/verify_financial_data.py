#!/usr/bin/env python3
"""
驗證已下載財報資料的完整性和正確性
"""

from pymongo import MongoClient
from collections import defaultdict
import json

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

def check_financial_data_quality():
    """檢查財報資料品質"""
    print("="*60)
    print("財報資料品質檢查")
    print("="*60)
    
    # 1. 統計已下載的股票
    downloaded_symbols = list(db.financial_statements.distinct('symbol'))
    print(f"\n1. 已下載股票數量: {len(downloaded_symbols)}")
    
    # 2. 檢查每支股票的季數
    quarters_dist = defaultdict(int)
    issues = []
    
    for symbol in downloaded_symbols:
        count = db.financial_statements.count_documents({'symbol': symbol})
        quarters_dist[count] += 1
        
        if count < 4:  # 少於 4 季可能有問題
            issues.append((symbol, count))
    
    print(f"\n2. 季數分布:")
    for q_count in sorted(quarters_dist.keys(), reverse=True)[:10]:
        print(f"   {q_count:2d} 季: {quarters_dist[q_count]:3d} 支股票")
    
    if issues:
        print(f"\n⚠️  發現 {len(issues)} 支股票資料少於 4 季:")
        for symbol, count in issues[:10]:
            company = db.stocks.find_one({'symbol': symbol})
            name = company['name'] if company else symbol
            print(f"   {symbol} {name}: {count} 季")
    
    # 3. 檢查資料結構完整性
    print(f"\n3. 資料結構檢查:")
    
    sample_docs = list(db.financial_statements.find().limit(100))
    
    has_balance_sheet = sum(1 for doc in sample_docs if doc.get('data', {}).get('balance_sheet'))
    has_income = sum(1 for doc in sample_docs if doc.get('data', {}).get('income_statement'))
    has_cashflow = sum(1 for doc in sample_docs if doc.get('data', {}).get('cashflow_statement'))
    
    print(f"   資產負債表: {has_balance_sheet}/{len(sample_docs)} ({has_balance_sheet/len(sample_docs)*100:.1f}%)")
    print(f"   損益表: {has_income}/{len(sample_docs)} ({has_income/len(sample_docs)*100:.1f}%)")
    print(f"   現金流量表: {has_cashflow}/{len(sample_docs)} ({has_cashflow/len(sample_docs)*100:.1f}%)")
    
    # 4. 檢查是否需要重整資料
    reorganized = db.financial_reports.count_documents({})
    print(f"\n4. 資料處理狀態:")
    print(f"   原始資料 (financial_statements): {db.financial_statements.count_documents({})}")
    print(f"   重整資料 (financial_reports): {reorganized}")
    
    if reorganized == 0:
        print(f"\n   ⚠️  需要執行資料重整: python3 scripts/reorganize_financial_data.py")
    
    # 5. 檢查財報資料的時間範圍
    print(f"\n5. 資料時間範圍:")
    pipeline = [
        {'$group': {
            '_id': '$symbol',
            'earliest': {'$min': '$date'},
            'latest': {'$max': '$date'},
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    
    top_stocks = list(db.financial_statements.aggregate(pipeline))
    for stock in top_stocks:
        company = db.stocks.find_one({'symbol': stock['_id']})
        name = company['name'] if company else stock['_id']
        print(f"   {stock['_id']} {name}: {stock['earliest']} ~ {stock['latest']} ({stock['count']} 季)")
    
    return {
        'total_stocks': len(downloaded_symbols),
        'total_quarters': db.financial_statements.count_documents({}),
        'issues': len(issues),
        'reorganized': reorganized > 0
    }

def verify_sample_calculations():
    """驗證範例股票的計算"""
    print(f"\n{'='*60}")
    print("範例股票計算驗證")
    print("="*60)
    
    # 檢查 2330, 2317, 2454 的 financial_reports
    test_symbols = ['2330', '2317', '2454']
    
    for symbol in test_symbols:
        report = db.financial_reports.find_one({
            'symbol': symbol,
            'fiscalYear': 2024,
            'fiscalPeriod': 'Q3'
        })
        
        if report:
            print(f"\n✓ {symbol} (2024 Q3) - 已重整")
            if 'ratios' in report and 'roe' in report['ratios']:
                print(f"  ROE: {report['ratios']['roe']:.2f}%")
                print(f"  淨利率: {report['ratios']['netMargin']:.2f}%")
        else:
            print(f"\n✗ {symbol} (2024 Q3) - 未重整或無資料")
    
    # 檢查原始資料
    print(f"\n原始資料檢查:")
    for symbol in test_symbols:
        count = db.financial_statements.count_documents({'symbol': symbol})
        print(f"  {symbol}: {count} 季財報")

if __name__ == '__main__':
    print("\n")
    quality_result = check_financial_data_quality()
    verify_sample_calculations()
    
    print(f"\n{'='*60}")
    print("檢查完成")
    print("="*60)
    
    if not quality_result['reorganized']:
        print("\n下一步:")
        print("1. 執行資料重整: python3 scripts/reorganize_financial_data.py")
        print("2. 驗證 DuPont 分析: curl http://localhost:3000/api/v1/financial/2330/dupont?year=2024&period=Q3")
    
    if quality_result['total_stocks'] < 1000:
        print(f"\n注意: 目前僅下載 {quality_result['total_stocks']} 支股票")
        print("等待 API 配額恢復後繼續下載")
