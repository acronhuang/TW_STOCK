#!/usr/bin/env python3
"""测试财务报表 API 获取股本数据"""

import requests
import os

token = os.getenv('FINMIND_API_TOKEN', '')
base_url = 'https://api.finmindtrade.com/api/v4/data'

# 测试数据集列表
test_datasets = [
    ('TaiwanStockFinancialStatements', '财务报表'),
    ('TaiwanStockBalanceSheet', '资产负债表'),
    ('TaiwanStockMonthRevenue', '月营收'),
    ('TaiwanStockPrice', '股价'),
]

for dataset, name in test_datasets:
    print("\n" + "=" * 80)
    print(f"{name} - {dataset}")
    print("=" * 80)
    
    params = {
        'dataset': dataset,
        'data_id': '2330',
        'start_date': '2025-01-01',
        'token': token
    }
    
    response = requests.get(base_url, params=params, timeout=15)
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        status = data.get('status')
        msg = data.get('msg')
        
        print(f"API Status: {status}, Message: {msg}")
        
        records = data.get('data', [])
        if records:
            print(f"记录数: {len(records)}")
            
            sample = records[0]
            print(f"\n字段列表 ({len(sample.keys())} 个):")
            
            # 寻找包含股本/股数相关的字段
            share_fields = []
            for key in sample.keys():
                lower_key = key.lower()
                if any(keyword in lower_key for keyword in ['share', 'capital', 'equity', 'stock', '股']):
                    share_fields.append(key)
                    print(f"  ✅ {key}: {sample[key]}")
            
            if not share_fields:
                print("  ❌ 未找到股本相关字段")
                print(f"\n所有字段: {list(sample.keys())}")
                
            # 显示第一笔完整数据
            print(f"\n第一笔数据:")
            for key, value in list(sample.items())[:10]:  # 只显示前10个字段
                print(f"  {key}: {value}")
                
            if len(sample.items()) > 10:
                print(f"  ... (共 {len(sample.items())} 个字段)")
        else:
            print("无数据")
    else:
        error_text = response.text[:500] if len(response.text) < 500 else response.text[:500] + "..."
        print(f"Error: {error_text}")

# 特别测试：直接获取股本资料
print("\n" + "=" * 80)
print("尝试 TaiwanStockStatisticsOfOrderBookAndTrade (委托统计)")
print("=" * 80)

params = {
    'dataset': 'TaiwanStockStatisticsOfOrderBookAndTrade',
    'data_id': '2330',
    'start_date': '2025-01-01',
    'token': token
}

response = requests.get(base_url, params=params, timeout=15)
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
    print(f"Error: {response.text[:300]}")

print("\n" + "=" * 80)
print("结论:")
print("=" * 80)
print("如果以上数据集都没有 outstanding_shares，")
print("建议方案:")
print("1. 从证交所网站爬取股本资料")
print("2. 使用资产负债表中的「股本」字段计算流通股数")
print("3. 使用 TEJ 或其他付费数据源")
print("=" * 80)
