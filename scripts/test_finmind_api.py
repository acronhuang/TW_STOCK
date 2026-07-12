#!/usr/bin/env python3
"""测试 FinMind API 数据集"""

import requests
import os

token = os.getenv('FINMIND_API_TOKEN', '')

base_url = 'https://api.finmindtrade.com/api/v4/data'

# 测试 1: TaiwanStockInfo (获取流通股数和股本)
print("=" * 80)
print("测试 TaiwanStockInfo (2330)")
print("=" * 80)
params = {
    'dataset': 'TaiwanStockInfo',
    'data_id': '2330',
    'token': token
}
response = requests.get(base_url, params=params)
print(f"HTTP Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"API Status: {data.get('status')}")
    print(f"Message: {data.get('msg')}")
    
    if data.get('data'):
        sample = data.get('data')[0] if len(data.get('data')) > 0 else {}
        print(f"\n可用字段: {list(sample.keys())}")
        print(f"\n2330 样本数据:")
        for key, value in sample.items():
            print(f"  {key}: {value}")
    else:
        print("无数据")
else:
    print(f"Error: {response.text[:300]}")

# 测试 2: TaiwanStockCapitalReduction (股票减资)
print("\n" + "=" * 80)
print("测试 TaiwanStockCapitalReduction (2330)")
print("=" * 80)
params = {
    'dataset': 'TaiwanStockCapitalReduction',
    'data_id': '2330',
    'start_date': '2000-01-01',
    'token': token
}
response = requests.get(base_url, params=params)
print(f"HTTP Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"API Status: {data.get('status')}")
    print(f"Message: {data.get('msg')}")
    events = data.get('data', [])
    print(f"减资事件数量: {len(events)}")
    
    if events:
        print(f"\n字段: {list(events[0].keys())}")
        print(f"\n前3笔减资事件:")
        for event in events[:3]:
            print(f"  {event}")
else:
    print(f"Error: {response.text[:300]}")

# 测试 3: TaiwanStockStatisticsOfOrderBookAndTrade (股本变化)
print("\n" + "=" * 80)
print("测试不同数据集获取股本信息")
print("=" * 80)

test_datasets = [
    'TaiwanStockSharesChange',  # 股本变动
    'TaiwanStockDailyShares',   # 每日流通股数
    'TaiwanStockPER',           # 本益比 (可能含市值)
]

for dataset in test_datasets:
    print(f"\n--- {dataset} ---")
    params = {
        'dataset': dataset,
        'data_id': '2330',
        'start_date': '2024-01-01',
        'token': token
    }
    response = requests.get(base_url, params=params)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"API Status: {data.get('status')}, Message: {data.get('msg')}")
        
        records = data.get('data', [])
        if records:
            print(f"记录数: {len(records)}")
            print(f"字段: {list(records[0].keys())}")
            print(f"样本: {records[0]}")
        else:
            print("无数据")
    else:
        print(f"Error: {response.text[:200]}")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
