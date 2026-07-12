#!/usr/bin/env python3
"""测试 ETF、权证及特殊代码过滤功能（完整版）"""

import sys
import logging
sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')

from src.downloaders.download_coordinator import DownloadCoordinator

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

# API Token
api_token = ""

# 初始化
coordinator = DownloadCoordinator(api_token=api_token, logger=logger)

# 测试数据（19 个用例）
test_symbols = [
    # 正常股票 (应保留)
    '2330',    # 台积电
    '2317',    # 鸿海
    '1216',    # 统一
    '1234',    # 正常股票
    
    # ETF - 4位数 (应过滤)
    '0050',    # 元大台湾50
    '0051',    # 元大中型100
    '0056',    # 元大高股息
    
    # ETF - 6位数 (应过滤)
    '006208',  # 富邦台50
    '006203',  # 元大摩台
    
    # ETF - 字母后缀 (应过滤)
    '00633L',  # 杠杆型 ETF
    '00634R',  # 反向 ETF
    '00635U',  # 黄金 ETF
    '00625K',  # ETF
    
    # 权证 (应过滤)
    '01004T',  # 权证
    '01007T',  # 权证
    '01008T',  # 权证
    
    # 特殊代码 - 02开头 (应过滤)
    '020000',  # 特殊代码
    '020001',  # 特殊代码
    
    # 其他衍生品 (应过滤)
    '02001B',  # 衍生品
]

print('\n' + '=' * 70)
print('🧪 ETF、權證及特殊代碼過濾測試（完整版）')
print('=' * 70)
print()

print(f'📋 原始列表（{len(test_symbols)} 支）:')
print('正常股票:')
print('  - 2330 (台积电)')
print('  - 2317 (鸿海)')
print('  - 1216 (统一)')
print('  - 1234 (正常股票)')
print()
print('ETF - 4位数:')
print('  - 0050 (元大台湾50)')
print('  - 0051 (元大中型100)')
print('  - 0056 (元大高股息)')
print()
print('ETF - 6位数:')
print('  - 006208 (富邦台50)')
print('  - 006203 (元大摩台)')
print()
print('ETF - 字母后缀:')
print('  - 00633L (杠杆型 ETF)')
print('  - 00634R (反向 ETF)')
print('  - 00635U (黄金 ETF)')
print('  - 00625K (ETF)')
print()
print('权证:')
print('  - 01004T, 01007T, 01008T')
print()
print('特殊代码:')
print('  - 020000, 020001')
print()
print('其他衍生品:')
print('  - 02001B')
print()

# 执行过滤
print('🔄 執行過濾...')
print()
filtered = coordinator._filter_etf(test_symbols)
print()

print(f'✅ 過濾後（{len(filtered)} 支）:')
for symbol in filtered:
    print(f'  - {symbol}')
print()

# 计算被过滤的代码
filtered_symbols = [s for s in test_symbols if s not in filtered]
print(f'❌ 已過濾（{len(filtered_symbols)} 支）:')
for symbol in filtered_symbols:
    print(f'  - {symbol}')
print()

print('=' * 70)
print('✅ 測試完成！')
print('=' * 70)
print()

# 验证结果
expected_kept = ['2330', '2317', '1216', '1234']
expected_filtered = [
    '0050', '0051', '0056',  # ETF 4位数
    '006208', '006203',  # ETF 6位数
    '00633L', '00634R', '00635U', '00625K',  # ETF 字母
    '01004T', '01007T', '01008T',  # 权证
    '020000', '020001',  # 特殊代码
    '02001B'  # 其他衍生品
]

if set(filtered) == set(expected_kept) and set(filtered_symbols) == set(expected_filtered):
    print('🎉 過濾邏輯完全正確！')
    print()
    print('📊 分類統計:')
    print(f'  ✅ 保留正常股票: {len(expected_kept)} 支')
    print(f'  ❌ 過濾 ETF (4位數): 3 支')
    print(f'  ❌ 過濾 ETF (6位數): 2 支')
    print(f'  ❌ 過濾 ETF (字母): 4 支')
    print(f'  ❌ 過濾權證: 3 支')
    print(f'  ❌ 過濾特殊代碼: 2 支')
    print(f'  ❌ 過濾其他衍生品: 1 支')
    print(f'  ❌ 過濾 ETF (6位數): 2 支')
    print(f'  ❌ 過濾 ETF (字母): 4 支')
    print(f'  ❌ 過濾權證: 3 支')
    print(f'  ❌ 過濾特殊代碼: 2 支')
    print(f'  ❌ 過濾其他衍生品: 1 支')
    print()
    sys.exit(0)
else:
    print('⚠️  結果不符合預期')
    print()
    print('預期保留:', expected_kept)
    print('實際保留:', filtered)
    print()
    print('預期過濾:', expected_filtered)
    print('實際過濾:', filtered_symbols)
    print()
    
    # 详细对比
    kept_missing = set(expected_kept) - set(filtered)
    kept_extra = set(filtered) - set(expected_kept)
    filtered_missing = set(expected_filtered) - set(filtered_symbols)
    filtered_extra = set(filtered_symbols) - set(expected_filtered)
    
    if kept_missing:
        print(f'❌ 应保留但被过滤: {kept_missing}')
    if kept_extra:
        print(f'❌ 不应保留但未过滤: {kept_extra}')
    if filtered_missing:
        print(f'❌ 应过滤但未过滤: {filtered_missing}')
    if filtered_extra:
        print(f'❌ 不应过滤但被过滤: {filtered_extra}')
    print()
    sys.exit(1)
