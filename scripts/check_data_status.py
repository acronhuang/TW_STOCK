#!/usr/bin/env python3
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

stats = {
    'stock_price': len([s for s in db.stock_price.distinct('stock_id') if s]),
    'financial': len([s for s in db.financial_reports.distinct('symbol') if s]),
    'per': len([s for s in db.taiwan_stock_per.distinct('stock_id') if s]),
    'dividend': len([s for s in db.dividend.distinct('stock_id') if s]),
    'holdings': len([s for s in db.institutional_holdings.distinct('stock_id') if s]),
    'trading': len([s for s in db.institutional_trading.distinct('stock_id') if s]),
    'total': len([s for s in db.stock_list.distinct('stock_id') if s])
}

print('='*70)
print('資料完整度狀態')
print('='*70)
for key, val in stats.items():
    if key == 'total':
        print(f'\n總股票數: {val}')
    else:
        pct = (val/stats['total']*100) if stats['total'] > 0 else 0
        status = '✓' if pct > 50 else '⚠️' if pct > 10 else '✗'
        print(f'{status} {key:20} {val:>4} / {stats["total"]} ({pct:>5.1f}%)')

print('='*70)
print('\n缺失數據集:')
missing = []
if stats['dividend'] == 0:
    missing.append('dividend')
if stats['holdings'] == 0:
    missing.append('institutional_holdings')
if stats['trading'] < stats['total'] * 0.5:
    missing.append('institutional_trading (下載中)')

if missing:
    for m in missing:
        print(f'  ✗ {m}')
else:
    print('  ✓ 所有數據集已完整')
print('='*70)
