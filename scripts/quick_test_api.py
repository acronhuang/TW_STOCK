#!/usr/bin/env python3
import os, sys
sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')

from src.downloaders.finmind_client import FinMindClient
from datetime import datetime, timedelta

api_token = os.getenv('FINMIND_API_TOKEN')
client = FinMindClient(api_token)

tables = [
    ('黃金', 'GoldPrice', {'start_date': '2026-02-20'}),
    ('原油', 'CrudeOilPrices', {'start_date': '2026-02-20'}),
    ('外匯', 'ExchangeRate', {'start_date': '2026-02-20'}),
    ('利率', 'GovernmentBondsYield', {'start_date': '2026-02-20'}),
    ('新聞', 'TaiwanStockNews', {'start_date': '2026-02-15', 'stock_id': '2330'})
]

print('=== 測試「其他」類別 API 可用性 ===\n')
ok = 0
for name, dataset, params in tables:
    try:
        data = client.fetch_data(dataset, params)
        count = len(data) if data else 0
        status = '✅' if count > 0 else '❌'
        if count > 0: ok += 1
        print(f'{status} {name:6s}: {count:5d} 筆')
    except Exception as e:
        print(f'❌ {name:6s}: 錯誤 - {str(e)[:60]}')

print(f'\n覆蓋率: {ok}/5 ({ok*20}%)')
