#!/usr/bin/env python3
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

print('=== taiwan_stock_per 各年份數據分佈 ===\n')

years = [2020, 2021, 2022, 2023, 2024, 2025]

for year in years:
    start = datetime(year, 1, 1)
    end = datetime(year+1, 1, 1) if year < 2025 else datetime(2025, 3, 1)
    
    count = db.taiwan_stock_per.count_documents({
        'date': {'$gte': start, '$lt': end}
    })
    
    # 檢查唯一日期數
    pipeline = [
        {'$match': {'date': {'$gte': start, '$lt': end}}},
        {'$group': {'_id': '$date'}},
        {'$count': 'unique_dates'}
    ]
    
    unique_dates_result = list(db.taiwan_stock_per.aggregate(pipeline))
    unique_dates = unique_dates_result[0]['unique_dates'] if unique_dates_result else 0
    
    print(f'{year}: {count:,} 筆記錄, {unique_dates} 個唯一日期')

# 檢查 2024 年的具體情況
print('\n=== 2024 年詳細分析 ===\n')

# 2024 年第一筆和最後一筆
first_2024 = list(db.taiwan_stock_per.find({
    'date': {'$gte': datetime(2024, 1, 1), '$lt': datetime(2025, 1, 1)}
}).sort('date', 1).limit(1))

last_2024 = list(db.taiwan_stock_per.find({
    'date': {'$gte': datetime(2024, 1, 1), '$lt': datetime(2025, 1, 1)}
}).sort('date', -1).limit(1))

if first_2024:
    print(f'最早日期: {first_2024[0]["date"].strftime("%Y-%m-%d")}')
if last_2024:
    print(f'最晚日期: {last_2024[0]["date"].strftime("%Y-%m-%d")}')

# 檢查 2024 年 2330 的數據
print('\n2330 in 2024:')
count_2330_2024 = db.taiwan_stock_per.count_documents({
    'stock_id': '2330',
    'date': {'$gte': datetime(2024, 1, 1), '$lt': datetime(2025, 1, 1)}
})
print(f'  數據筆數: {count_2330_2024}')

# 抽樣 10 筆
samples = list(db.taiwan_stock_per.find({
    'stock_id': '2330',
    'date': {'$gte': datetime(2024, 1, 1), '$lt': datetime(2025, 1, 1)}
}).sort('date', 1).limit(10))

for doc in samples:
    date = doc['date'].strftime('%Y-%m-%d')
    per = doc.get('PER')
    pbr = doc.get('PBR')
    print(f'  {date}: PER={per}, PBR={pbr}')

client.close()
