#!/usr/bin/env python3
"""测试 ETF 过滤功能"""

import sys
import os
import logging

sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')

from src.downloaders.download_coordinator import DownloadCoordinator

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

# API Token
api_token = ""

# 初始化
coordinator = DownloadCoordinator(
    api_token=api_token,
    logger=logger
)

# 测试数据
test_symbols = [
    '2330',    # 台积电（正常股票）✅
    '2317',    # 鸿海（正常股票）✅
    '0050',    # 元大台湾50（4位数 ETF，应保留）✅
    '006208',  # 富邦台50（6位数 ETF，应过滤）❌
    '00633L',  # 杠杆型 ETF（应过滤）❌
    '00634R',  # 反向 ETF（应过滤）❌
    '00635U',  # 黄金 ETF（应过滤）❌
    '00625K',  # ETF（应过滤）❌
    '1234',    # 正常股票✅
]

print("\n" + "="*70)
print("🧪 ETF 过滤功能测试")
print("="*70)

print(f"\n📋 原始列表（{len(test_symbols)} 支）:")
for sym in test_symbols:
    print(f"  - {sym}")

# 执行过滤
filtered = coordinator._filter_etf(test_symbols)

print(f"\n✅ 过滤后（{len(filtered)} 支）:")
for sym in filtered:
    print(f"  - {sym}")

excluded = [s for s in test_symbols if s not in filtered]
print(f"\n❌ 已过滤（{len(excluded)} 支）:")
for sym in excluded:
    print(f"  - {sym}")

print("\n" + "="*70)
print("✅ 测试完成！")
print("="*70)

# 验证结果
expected_kept = ['2330', '2317', '0050', '1234']
expected_filtered = ['006208', '00633L', '00634R', '00635U', '00625K']

if set(filtered) == set(expected_kept):
    print("\n🎉 过滤逻辑正确！")
    sys.exit(0)
else:
    print("\n⚠️  结果不符合预期")
    print(f"预期保留: {expected_kept}")
    print(f"实际保留: {filtered}")
    sys.exit(1)
