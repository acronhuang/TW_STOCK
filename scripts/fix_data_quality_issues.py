#!/usr/bin/env python3
"""修復資料品質問題"""

import pymongo
from datetime import datetime

client = pymongo.MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print("=" * 70)
print("自動修復資料品質問題")
print("=" * 70)

# 1. 修復零資產財報
print("\n【1. 修復零資產財報】")
zero_assets = list(db.financial_reports.find({
    'balanceSheet.totalAssets': {'$in': [0, None]}
}, {'symbol': 1, 'fiscalYear': 1, 'fiscalPeriod': 1}))

if zero_assets:
    print(f"發現 {len(zero_assets)} 筆零資產財報:")
    for r in zero_assets:
        symbol = r['symbol']
        year = r.get('fiscalYear')
        period = r.get('fiscalPeriod')
        print(f"  {symbol} {year}{period}")
        
        # 刪除這些異常資料
        result = db.financial_reports.delete_one({'_id': r['_id']})
        if result.deleted_count > 0:
            print(f"    ✓ 已刪除")
else:
    print("✓ 無零資產財報")

# 2. 修復缺少 ROE 的財報
print("\n【2. 修復缺少 ROE 的財報】")
missing_roe = list(db.financial_reports.find({
    'ratios.roe': {'$in': [None, 0]},
    'incomeStatement.netIncome': {'$ne': None},
    'balanceSheet.equity': {'$gt': 0}
}))

if missing_roe:
    print(f"發現 {len(missing_roe)} 筆缺少 ROE 的財報")
    fixed_count = 0
    
    for r in missing_roe:
        net_income = r['incomeStatement']['netIncome']
        equity = r['balanceSheet']['equity']
        roe = (net_income / equity) * 100
        
        # 更新 ROE
        result = db.financial_reports.update_one(
            {'_id': r['_id']},
            {'$set': {'ratios.roe': roe}}
        )
        
        if result.modified_count > 0:
            fixed_count += 1
            if fixed_count <= 3:
                print(f"  ✓ {r['symbol']} {r.get('fiscalYear', 'N/A')}{r.get('fiscalPeriod', 'N/A')}: ROE={roe:.2f}%")
    
    print(f"✓ 已修復 {fixed_count}/{len(missing_roe)} 筆 ROE")
else:
    print("✓ 所有財報都有 ROE")

# 3. 修復缺少公司名稱的財報
print("\n【3. 修復缺少公司名稱的財報】")
missing_names = list(db.financial_reports.find({
    '$or': [
        {'companyName': {'$in': [None, '']}},
        {'companyName': {'$regex': '^[0-9]{4}$'}}
    ]
}, {'symbol': 1, 'companyName': 1}).limit(400))

if missing_names:
    print(f"發現 {len(missing_names)} 筆缺少公司名稱的財報")
    fixed_count = 0
    
    for r in missing_names:
        symbol = r['symbol']
        
        # 從 tickers 或 stocks 查詢公司名稱
        ticker = db.tickers.find_one({'stock_id': symbol})
        stock = db.stocks.find_one({'stock_id': symbol})
        
        name = None
        if ticker and ticker.get('name'):
            name = ticker['name']
        elif stock and stock.get('name'):
            name = stock['name']
        
        if name and name != symbol:  # 確保不是只有股票代碼
            result = db.financial_reports.update_many(
                {'symbol': symbol},
                {'$set': {'companyName': name}}
            )
            
            if result.modified_count > 0:
                fixed_count += result.modified_count
                if fixed_count <= 10:
                    print(f"  ✓ {symbol} → {name} ({result.modified_count} 筆)")
    
    print(f"✓ 已修復 {fixed_count} 筆公司名稱")
else:
    print("✓ 所有財報都有公司名稱")

# 4. 驗證修復結果
print("\n" + "=" * 70)
print("修復結果驗證")
print("=" * 70)

# 重新檢查
total = db.financial_reports.count_documents({})
zero_assets_after = db.financial_reports.count_documents({
    'balanceSheet.totalAssets': {'$in': [0, None]}
})
missing_roe_after = db.financial_reports.count_documents({
    'ratios.roe': {'$in': [None, 0]}
})
missing_names_after = db.financial_reports.count_documents({
    '$or': [
        {'companyName': {'$in': [None, '']}},
        {'companyName': {'$regex': '^[0-9]{4}$'}}
    ]
})

print(f"\n零資產財報: {zero_assets_after}/{total}")
print(f"缺少 ROE: {missing_roe_after}/{total} ({missing_roe_after/total*100:.1f}%)")
print(f"缺少公司名稱: {missing_names_after}/{total} ({missing_names_after/total*100:.1f}%)")

if zero_assets_after == 0 and missing_roe_after == 0 and missing_names_after < 50:
    print("\n✅ 所有問題已修復！")
else:
    print(f"\n⚠️  仍有 {zero_assets_after + missing_roe_after + missing_names_after} 筆需要處理")

print("\n修復完成時間:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
