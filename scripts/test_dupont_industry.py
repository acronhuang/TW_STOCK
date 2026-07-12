#!/usr/bin/env python3
"""
測試杜邦分析的產業判斷邏輯
"""

import requests
import json
from pymongo import MongoClient

# 連接資料庫
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 測試數據：不同產業的模擬財報
test_cases = [
    {
        'symbol': 'TEST_SEMI',
        'companyName': '測試半導體公司',
        'fiscalYear': 2025,
        'fiscalPeriod': 'Q1',
        'incomeStatement': {
            'revenue': 100000000,      # 1億
            'grossProfit': 55000000,   # 毛利率 55%
            'operatingIncome': 45000000,
            'netIncome': 40000000,     # 淨利率 40%
            'grossMargin': 55.0,
            'operatingMargin': 45.0,
            'netMargin': 40.0,
        },
        'balanceSheet': {
            'totalAssets': 250000000,  # 2.5億，週轉率 0.4
            'equity': 200000000,
            'totalLiabilities': 50000000,
        },
        'ratios': {'roe': 20.0},
        'dataSource': 'Test',
        'industry': '半導體製造'
    },
    {
        'symbol': 'TEST_RETAIL',
        'companyName': '測試零售公司',
        'fiscalYear': 2025,
        'fiscalPeriod': 'Q1',
        'incomeStatement': {
            'revenue': 500000000,      # 5億
            'grossProfit': 100000000,  # 毛利率 20%
            'operatingIncome': 30000000,
            'netIncome': 25000000,     # 淨利率 5%
            'grossMargin': 20.0,
            'operatingMargin': 6.0,
            'netMargin': 5.0,
        },
        'balanceSheet': {
            'totalAssets': 200000000,  # 2億，週轉率 2.5
            'equity': 150000000,
            'totalLiabilities': 50000000,
        },
        'ratios': {'roe': 16.7},
        'dataSource': 'Test',
        'industry': '零售服務'
    },
    {
        'symbol': 'TEST_MFG',
        'companyName': '測試傳統製造',
        'fiscalYear': 2025,
        'fiscalPeriod': 'Q1',
        'incomeStatement': {
            'revenue': 300000000,      # 3億
            'grossProfit': 90000000,   # 毛利率 30%
            'operatingIncome': 45000000,
            'netIncome': 36000000,     # 淨利率 12%
            'grossMargin': 30.0,
            'operatingMargin': 15.0,
            'netMargin': 12.0,
        },
        'balanceSheet': {
            'totalAssets': 300000000,  # 3億，週轉率 1.0
            'equity': 200000000,
            'totalLiabilities': 100000000,
        },
        'ratios': {'roe': 18.0},
        'dataSource': 'Test',
        'industry': '傳統製造'
    }
]

print("=" * 80)
print("插入測試財報數據")
print("=" * 80)

for test_data in test_cases:
    # 刪除舊的測試數據
    db.financial_reports.delete_many({'symbol': test_data['symbol']})
    
    # 插入新的測試數據
    db.financial_reports.insert_one(test_data)
    print(f"✅ {test_data['symbol']} - {test_data['companyName']} (預期產業: {test_data['industry']})")

print("\n" + "=" * 80)
print("測試杜邦分析 API")
print("=" * 80)

for test_data in test_cases:
    symbol = test_data['symbol']
    expected_industry = test_data['industry']
    
    print(f"\n{'=' * 80}")
    print(f"測試 {symbol} - {test_data['companyName']}")
    print(f"預期產業: {expected_industry}")
    print("=" * 80)
    
    # 呼叫 API
    url = f"http://localhost:3000/api/v1/financial/{symbol}/dupont"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        analysis = data.get('analysis', {})
        
        print(f"\n偵測產業: {analysis.get('industryType', 'N/A')}")
        print(f"資產週轉率: {data.get('assetTurnover', 0):.4f}")
        print(f"淨利率: {data.get('netMargin', 0):.2f}%")
        print(f"毛利率: {data.get('fiveStepDecomposition', {}).get('grossMargin', 0):.2f}%")
        
        print("\n✅ 優勢:")
        for strength in analysis.get('strengths', []):
            print(f"   • {strength}")
        
        print("\n⚠️  劣勢:")
        for weakness in analysis.get('weaknesses', []):
            print(f"   • {weakness}")
        
        print("\n💡 建議:")
        for rec in analysis.get('recommendations', []):
            print(f"   • {rec}")
        
        # 驗證產業判斷是否正確
        detected = analysis.get('industryType', '')
        if detected == expected_industry:
            print(f"\n✅ 產業判斷正確！ ({detected})")
        else:
            print(f"\n❌ 產業判斷錯誤！偵測為 {detected}，預期為 {expected_industry}")
    else:
        print(f"❌ API 錯誤: {response.status_code}")
        print(response.text)

print("\n" + "=" * 80)
print("測試完成！")
print("=" * 80)

# 清理測試數據（可選）
cleanup = input("\n是否清理測試數據？(y/N): ")
if cleanup.lower() == 'y':
    for test_data in test_cases:
        db.financial_reports.delete_many({'symbol': test_data['symbol']})
    print("✅ 測試數據已清理")

client.close()
