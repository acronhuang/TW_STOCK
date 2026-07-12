#!/usr/bin/env python3
"""分析数据库中的特殊代码类型"""

import pymongo
from collections import defaultdict

client = pymongo.MongoClient('mongodb://localhost:27017/')
db = client.tw_stock_analysis

codes = db.taiwan_stock_info.distinct('stock_id')

special = defaultdict(list)

for code in codes:
    if not code:
        continue
    
    # ETF（已过滤）
    if code.startswith('00') and len(code) >= 5:
        if len(code) == 6 and code.isdigit():
            special['etf_6digit'].append(code)
        elif len(code) >= 5 and code[:4].isdigit() and code[4].isalpha():
            special['etf_with_letter'].append(code)
    # 权证（5位数+T）
    elif len(code) == 6 and code[:5].isdigit() and code.endswith('T'):
        special['warrant_t'].append(code)
    # 其他6位数（02开头）
    elif len(code) == 6 and code.startswith('02') and code.isdigit():
        special['other_6digit'].append(code)
    # 其他字母后缀（非T）
    elif len(code) == 6 and code[:5].isdigit() and code[5].isalpha() and not code.endswith('T'):
        special['other_with_letter'].append(code)

print('======================================')
print('特殊代码统计：')
print('======================================')
print(f'ETF (6位数，如 006208): {len(special["etf_6digit"])} 个')
print(f'ETF (字母后缀，如 00633L): {len(special["etf_with_letter"])} 个')
print(f'权证 (5位数+T，如 01004T): {len(special["warrant_t"])} 个')
print(f'其他 (6位数，如 020000): {len(special["other_6digit"])} 个')
print(f'其他 (5位数+字母): {len(special["other_with_letter"])} 个')
print()
print('💡 建议过滤的代码类型：')
print(f'   - 权证 (xxxT): {len(special["warrant_t"])} 个')
print(f'   - 其他特殊: {len(special["other_6digit"]) + len(special["other_with_letter"])} 个')
print()

total_to_filter = len(special["warrant_t"]) + len(special["other_6digit"]) + len(special["other_with_letter"])
print(f'🎯 总共需要额外过滤: {total_to_filter} 个代码')
print()

if special['warrant_t']:
    print('权证示例:', ', '.join(sorted(special['warrant_t'])[:10]))
if special['other_6digit']:
    print('其他6位数示例:', ', '.join(sorted(special['other_6digit'])[:10]))
if special['other_with_letter']:
    print('其他字母示例:', ', '.join(sorted(special['other_with_letter'])[:10]))

client.close()
