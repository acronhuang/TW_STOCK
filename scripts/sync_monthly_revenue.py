#!/usr/bin/env python3
"""
monthly_revenue 月營收同步腳本

功能：
1. 檢查本地 monthly_revenue 最新月份
2. 從 FinMind API 逐股拉取缺少月份的 TaiwanStockMonthRevenue
3. 單位轉換（FinMind 用「元」，本地用「千元」）
4. 計算 MoM / YoY 成長率
5. upsert 到本地 monthly_revenue

執行方式：
  python3 scripts/sync_monthly_revenue.py                # 自動補最新月份
  python3 scripts/sync_monthly_revenue.py --month 2026-02  # 指定月份
  python3 scripts/sync_monthly_revenue.py --limit 500    # 限制 API 呼叫次數
"""

import os, sys, time, logging, argparse
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
load_dotenv()

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
TOKEN = os.getenv('FINMIND_API_TOKEN', '')
FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'


def get_target_month(db):
    """自動偵測需要補充的月份"""
    # 找本地最新月份
    latest = list(db.monthly_revenue.find({}, {'year_month': 1}).sort('year_month', -1).limit(1))
    if not latest:
        return '2026-01'
    latest_ym = latest[0]['year_month']

    # 計算下一個月
    y, m = int(latest_ym[:4]), int(latest_ym[5:7])
    m += 1
    if m > 12:
        m = 1
        y += 1
    return f'{y:04d}-{m:02d}'


def fetch_revenue(symbol, start_date):
    """從 FinMind 取得月營收"""
    r = requests.get(FINMIND_URL, params={
        'dataset': 'TaiwanStockMonthRevenue',
        'data_id': symbol,
        'start_date': start_date,
        'token': TOKEN
    }, timeout=15)
    if r.status_code == 402:
        return None  # 配額耗盡
    if r.status_code != 200:
        return []
    return r.json().get('data', [])


def main():
    parser = argparse.ArgumentParser(description='同步月營收')
    parser.add_argument('--month', type=str, help='指定月份 (YYYY-MM)')
    parser.add_argument('--limit', type=int, default=550, help='API 呼叫上限 (預設 550)')
    parser.add_argument('--sym', type=str, help='只更新單一股票')
    args = parser.parse_args()

    client = MongoClient(MONGO_URI)
    db = client['tw_stock_analysis']

    # 決定目標月份
    target_ym = args.month or get_target_month(db)
    target_y, target_m = int(target_ym[:4]), int(target_ym[5:7])

    # FinMind 的 date 欄位：revenue_month=2 對應 date=YYYY-03-01
    # 所以查詢 start_date 要用目標月份+1
    fm_m = target_m + 1
    fm_y = target_y
    if fm_m > 12:
        fm_m = 1
        fm_y += 1
    fm_start = f'{fm_y:04d}-{fm_m:02d}-01'

    logger.info(f'目標月份: {target_ym} | FinMind 查詢日期: {fm_start}')

    # 取股票清單
    if args.sym:
        symbols = [args.sym]
    else:
        symbols = sorted(db.monthly_revenue.distinct('symbol'))
        if not symbols:
            symbols = sorted(db.stock_factors.distinct('symbol'))

    # 排除已有資料的
    existing = set(d['symbol'] for d in db.monthly_revenue.find(
        {'year_month': target_ym}, {'symbol': 1}
    ))
    missing = [s for s in symbols if s not in existing]

    logger.info(f'股票總數: {len(symbols)} | 已有: {len(existing)} | 需補: {len(missing)}')

    if not missing:
        logger.info('全部已同步，無需更新')
        return

    batch = missing[:args.limit]
    logger.info(f'本次處理: {len(batch)} 支（上限 {args.limit}）')

    # 預載名稱和產業
    name_map = {}
    for r in db.monthly_revenue.find(
        {'year_month': {'$exists': True}},
        {'symbol': 1, 'name': 1, 'industry': 1}
    ):
        if r['symbol'] not in name_map:
            name_map[r['symbol']] = {
                'name': r.get('name', ''),
                'industry': r.get('industry', '')
            }

    # 計算上月和去年同期的 year_month
    prev_m = target_m - 1
    prev_y = target_y
    if prev_m < 1:
        prev_m = 12
        prev_y -= 1
    prev_ym = f'{prev_y:04d}-{prev_m:02d}'
    yoy_ym = f'{target_y - 1:04d}-{target_m:02d}'

    new_count = 0
    api_count = 0
    no_data = 0

    for i, sym in enumerate(batch):
        data = fetch_revenue(sym, fm_start)
        api_count += 1

        if data is None:
            logger.warning(f'⚠️  API 配額耗盡，已處理 {i}/{len(batch)}')
            break

        # 找目標月份的記錄
        found = False
        for d in data:
            if d.get('revenue_year') == target_y and d.get('revenue_month') == target_m:
                rev = d['revenue'] / 1000  # 元 → 千元
                info = name_map.get(sym, {})

                doc = {
                    'symbol': sym,
                    'year_month': target_ym,
                    'revenue': rev,
                    'name': info.get('name', ''),
                    'industry': info.get('industry', ''),
                    'data_source': 'FinMind',
                    'updated_at': datetime.now(timezone.utc),
                }

                # MoM
                prev = db.monthly_revenue.find_one({'symbol': sym, 'year_month': prev_ym})
                if prev and prev.get('revenue') and prev['revenue'] > 0:
                    doc['mom_growth'] = (rev - prev['revenue']) / prev['revenue'] * 100
                    doc['last_month_revenue'] = prev['revenue']

                # YoY
                yoy_doc = db.monthly_revenue.find_one({'symbol': sym, 'year_month': yoy_ym})
                if yoy_doc and yoy_doc.get('revenue') and yoy_doc['revenue'] > 0:
                    doc['yoy_growth'] = (rev - yoy_doc['revenue']) / yoy_doc['revenue'] * 100
                    doc['last_year_revenue'] = yoy_doc['revenue']

                db.monthly_revenue.update_one(
                    {'symbol': sym, 'year_month': target_ym},
                    {'$set': doc},
                    upsert=True
                )
                new_count += 1
                found = True
                break

        if not found:
            no_data += 1

        if (i + 1) % 50 == 0:
            logger.info(f'進度: {i+1}/{len(batch)} | 新增: {new_count} | 無資料: {no_data}')

        time.sleep(0.1)

    logger.info('')
    logger.info('=' * 50)
    target_count = db.monthly_revenue.count_documents({'year_month': target_ym})
    total_count = db.monthly_revenue.count_documents({})
    logger.info(f'完成！新增: {new_count} | 無資料: {no_data} | API: {api_count} 次')
    logger.info(f'{target_ym} 月營收: {target_count} 支')
    logger.info(f'monthly_revenue 總筆數: {total_count:,}')

    if api_count >= args.limit or (data is None):
        logger.warning(f'⚠️  配額不足或達上限，下次再繼續補充')


if __name__ == '__main__':
    main()
