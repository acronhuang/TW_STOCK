#!/usr/bin/env python3
"""查找资产负债表中的股本数据"""

import requests
import os

token = os.getenv('FINMIND_API_TOKEN', '')

print("=" * 80)
print("查找台积电 (2330) 的股本数据")
print("=" * 80)

params = {
    'dataset': 'TaiwanStockBalanceSheet',
    'data_id': '2330',
    'start_date': '2024-01-01',
    'token': token
}

response = requests.get('https://api.finmindtrade.com/api/v4/data', params=params, timeout=15)
data = response.json()

records = data.get('data', [])
print(f"\n资产负债表记录数: {len(records)}")

if not records:
    print("无数据！")
    exit(1)

# 查找所有唯一的 type 和 origin_name
types_dict = {}
for record in records:
    type_name = record.get('type', '')
    origin_name = record.get('origin_name', '')
    key = f"{type_name}"
    if key not in types_dict:
        types_dict[key] = origin_name

print(f"\n所有科目类型 (共 {len(types_dict)} 个):")
for type_name in sorted(types_dict.keys()):
    origin = types_dict[type_name]
    print(f"  {type_name}: {origin}")

# 特别查找股本相关
print(f"\n" + "=" * 80)
print("🔍 查找包含「股本」「資本」「Capital」的科目:")
print("=" * 80)

capital_types = []
for type_name, origin_name in types_dict.items():
    if any(keyword in type_name for keyword in ['Capital', 'Share', 'Equity']) or \
       any(keyword in origin_name for keyword in ['股本', '資本', '股數']):
        capital_types.append((type_name, origin_name))
        print(f"  ✅ {type_name}: {origin_name}")

if not capital_types:
    print("  ❌ 未找到股本相关科目")

# 查找最新的股本数据
latest_date = max([r['date'] for r in records])
print(f"\n" + "=" * 80)
print(f"最新日期: {latest_date}")
print("=" * 80)

# 筛选股本相关的记录
capital_records = [
    r for r in records 
    if ('Capital' in r.get('type', '') or 
        'Equity' in r.get('type', '') or
        '股本' in r.get('origin_name', '') or
        '資本' in r.get('origin_name', '')) and
    r['date'] == latest_date
]

if capital_records:
    print(f"\n股本相关数据 ({latest_date}):")
    for r in sorted(capital_records, key=lambda x: x.get('origin_name', '')):
        value = r.get('value', 0)
        print(f"\n  {r['origin_name']}:")
        print(f"    类型: {r['type']}")
        print(f"    金额: {value:,.0f} 元")
        
        # 如果是股本，计算流通股数
        if '股本' in r['origin_name'] and 'Capital' in r['type']:
            # 台湾股票面额通常是 10 元/股
            par_value = 10
            shares = value / par_value
            print(f"    📊 流通股数: {shares:,.0f} 股")
            print(f"    📊 流通股数: {shares/1000:,.0f} 千股")
            print(f"    计算方式: 股本 {value:,.0f} / 面额 {par_value} = {shares:,.0f} 股")
else:
    print("\n❌ 未找到股本数据")

# 测试几个常见的股票
print(f"\n" + "=" * 80)
print("测试其他股票的股本数据")
print("=" * 80)

test_stocks = ['2330', '2317', '2454', '2881']
for stock_id in test_stocks:
    params['data_id'] = stock_id
    response = requests.get('https://api.finmindtrade.com/api/v4/data', params=params, timeout=15)
    data = response.json()
    
    records = data.get('data', [])
    if records:
        latest_date = max([r['date'] for r in records])
        capital_record = next(
            (r for r in records if r['date'] == latest_date and 'Capital' in r['type'] and '股本' in r.get('origin_name', '')),
            None
        )
        
        if capital_record:
            value = capital_record.get('value', 0)
            shares = value / 10
            print(f"  {stock_id}: 股本 {value/1e8:,.2f} 億, 流通股数 {shares/1e9:,.2f} 十億股")
        else:
            print(f"  {stock_id}: ❌ 未找到股本")
    else:
        print(f"  {stock_id}: ❌ 无数据")

print(f"\n" + "=" * 80)
print("结论")
print("=" * 80)
print("✅ 可以从 TaiwanStockBalanceSheet 的「股本」科目获取流通股数")
print("✅ 计算公式: 流通股数 = 股本金额 / 10 (面额)")
print("✅ 下一步: 创建下载器批量更新 taiwan_stock_info.outstanding_shares")
print("=" * 80)
