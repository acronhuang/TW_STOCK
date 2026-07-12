#!/usr/bin/env python3
"""
快速建立 2330 的假數據用於測試杜邦分析
（使用合理的財報數字）
"""

from pymongo import MongoClient
from datetime import datetime

def create_test_financial_data():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 使用接近真實的 2330 財報數據（單位：千元）
    test_data = [
        {
            'symbol': '2330',
            'companyName': '台積電',
            'fiscalYear': 2024,
            'fiscalPeriod': 'Q3',
            'dataSource': 'Test Data',
            'incomeStatement': {
                'revenue': 759690000,  # 營收 7597 億
                'grossProfit': 368000000,  # 毛利
                'operatingIncome': 303000000,  # 營業利益
                'netIncome': 325000000,  # 淨利
                'grossMargin': 48.4,  # 毛利率
                'operatingMargin': 39.9,  # 營益率
                'netMargin': 42.8  # 淨利率
            },
            'balanceSheet': {
                'totalAssets': 6500000000,  # 總資產 6.5 兆
                'equity': 3750000000,  # 股東權益 3.75 兆
                'currentAssets': 3000000000,
                'fixedAssets': 3000000000,
                'totalLiabilities': 2750000000
            },
            'ratios': {
                'roe': 8.67,  # ROE
                'roa': 5.0,  # ROA
                'grossMargin': 48.4,
                'operatingMargin': 39.9,
                'netMargin': 42.8
            },
            'updateTime': datetime.now()
        },
        {
            'symbol': '2330',
            'companyName': '台積電',
            'fiscalYear': 2024,
            'fiscalPeriod': 'Q2',
            'dataSource': 'Test Data',
            'incomeStatement': {
                'revenue': 673510000,
                'grossProfit': 337000000,
                'operatingIncome': 275000000,
                'netIncome': 247850000,
                'grossMargin': 50.0,
                'operatingMargin': 40.8,
                'netMargin': 36.8
            },
            'balanceSheet': {
                'totalAssets': 6400000000,
                'equity': 3700000000,
                'currentAssets': 2950000000,
                'fixedAssets': 2950000000,
                'totalLiabilities': 2700000000
            },
            'ratios': {
                'roe': 6.7,
                'roa': 3.9,
                'grossMargin': 50.0,
                'operatingMargin': 40.8,
                'netMargin': 36.8
            },
            'updateTime': datetime.now()
        },
        {
            'symbol': '2330',
            'companyName': '台積電',
            'fiscalYear': 2024,
            'fiscalPeriod': 'Q1',
            'dataSource': 'Test Data',
            'incomeStatement': {
                'revenue': 592640000,
                'grossProfit': 311000000,
                'operatingIncome': 255000000,
                'netIncome': 225490000,
                'grossMargin': 52.4,
                'operatingMargin': 43.0,
                'netMargin': 38.0
            },
            'balanceSheet': {
                'totalAssets': 6300000000,
                'equity': 3650000000,
                'currentAssets': 2900000000,
                'fixedAssets': 2900000000,
                'totalLiabilities': 2650000000
            },
            'ratios': {
                'roe': 6.2,
                'roa': 3.6,
                'grossMargin': 52.4,
                'operatingMargin': 43.0,
                'netMargin': 38.0
            },
            'updateTime': datetime.now()
        }
    ]
    
    print("=" * 80)
    print("建立 2330 測試財報數據")
    print("=" * 80)
    
    # 寫入到 financial_reports 集合（NestJS 使用的集合）
    saved = 0
    for data in test_data:
        result = db.financial_reports.update_one(
            {
                'symbol': data['symbol'],
                'fiscalYear': data['fiscalYear'],
                'fiscalPeriod': data['fiscalPeriod']
            },
            {'$set': data},
            upsert=True
        )
        
        if result.upserted_id or result.modified_count > 0:
            saved += 1
            print(f"\n✅ {data['fiscalYear']}{data['fiscalPeriod']}")
            print(f"   營收: {data['incomeStatement']['revenue']:,.0f}")
            print(f"   淨利: {data['incomeStatement']['netIncome']:,.0f}")
            print(f"   總資產: {data['balanceSheet']['totalAssets']:,.0f}")
            print(f"   股東權益: {data['balanceSheet']['equity']:,.0f}")
            print(f"   ROE: {data['ratios']['roe']:.2f}%")
    
    print(f"\n{'='*80}")
    print(f"✅ 完成！共儲存 {saved} 筆財報")
    print(f"{'='*80}")
    
    # 驗證
    print(f"\nfinancial_reports 集合記錄數: {db.financial_reports.count_documents({})}")
    print(f"2330 財報數: {db.financial_reports.count_documents({'symbol': '2330'})}")

if __name__ == '__main__':
    create_test_financial_data()
