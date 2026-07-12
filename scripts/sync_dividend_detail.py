#!/usr/bin/env python3
"""
dividend_detail 增量同步腳本

功能：
1. 找出本地 dividend_detail 缺少資料的股票（與 stock_factors 比對）
2. 從 FinMind API 拉取 TaiwanStockDividend
3. 比對差異後 upsert 到本地 dividend_detail
4. 每次執行只補缺口，不重複拉已有資料（節省 API 配額）

執行方式：
  python3 scripts/sync_dividend_detail.py               # 只補缺少的股票
  python3 scripts/sync_dividend_detail.py --all         # 強制更新所有股票（耗配額）
  python3 scripts/sync_dividend_detail.py --sym 2330    # 只更新單一股票
"""

import os, sys, re, time, logging, argparse
from datetime import datetime, timedelta
from collections import defaultdict
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
load_dotenv()

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
TOKEN = os.getenv('FINMIND_API_TOKEN')
DB_NAME = 'tw_stock_analysis'
START_DATE = '2015-01-01'


def parse_year(year_str):
    m = re.match(r'^(\d+)', str(year_str or ''))
    return int(m.group(1)) if m else None


def fetch_finmind_dividend(symbol: str, token: str) -> list:
    """從 FinMind 拉取股利資料"""
    try:
        r = requests.get('https://api.finmindtrade.com/api/v4/data', params={
            'dataset': 'TaiwanStockDividend',
            'data_id': symbol,
            'start_date': START_DATE,
            'token': token
        }, timeout=15)
        if r.status_code == 402:
            logger.warning('⚠️  API 配額已達上限，停止執行')
            return None  # None 表示配額耗盡
        if r.status_code == 200 and r.json().get('msg') == 'success':
            return r.json().get('data', [])
    except Exception as e:
        logger.debug(f'{symbol} API 錯誤: {e}')
    return []


def api_to_db_record(api_rec: dict) -> dict:
    """將 FinMind API 格式轉為 dividend_detail 格式"""
    def to_num(v):
        try: return float(v) if v is not None else 0.0
        except: return 0.0

    yr_raw = api_rec.get('year', '')
    yr_int = parse_year(yr_raw)
    # 民國年轉西元
    ce_year = yr_int + 1911 if yr_int and yr_int < 200 else yr_int

    return {
        'stock_id': api_rec.get('stock_id'),
        'date': api_rec.get('date'),
        'year': str(yr_int) if yr_int else yr_raw,  # 統一儲存民國年數字
        'announcement_date': api_rec.get('AnnouncementDate', ''),
        'cash_ex_dividend_date': api_rec.get('CashExDividendTradingDate', ''),
        'cash_earnings_distribution': to_num(api_rec.get('CashEarningsDistribution')),
        'cash_statutory_surplus': to_num(api_rec.get('CashStatutorySurplus')),
        'stock_earnings_distribution': to_num(api_rec.get('StockEarningsDistribution')),
        'stock_statutory_surplus': to_num(api_rec.get('StockStatutorySurplus')),
        'stock_ex_dividend_date': api_rec.get('StockExDividendTradingDate', ''),
        'participate_distribution_shares': to_num(api_rec.get('ParticipateDistributionOfTotalShares')),
        'data_source': 'FinMind',
        'updated_at': datetime.now(),
    }


def sync_symbol(db, symbol: str, token: str, force: bool = False) -> dict:
    """同步單一股票的股利資料，回傳統計"""
    stats = {'new': 0, 'updated': 0, 'unchanged': 0, 'skipped': False}

    # 檢查本地最新資料日期
    latest_local = db.dividend_detail.find_one(
        {'stock_id': symbol},
        sort=[('date', -1)]
    )

    if not force and latest_local:
        # 若本地已有近期資料（6個月內），跳過
        try:
            latest_date = datetime.strptime(latest_local['date'][:10], '%Y-%m-%d')
            if datetime.now() - latest_date < timedelta(days=180):
                stats['skipped'] = True
                return stats
        except:
            pass

    # 拉 API
    api_data = fetch_finmind_dividend(symbol, token)
    if api_data is None:
        return None  # 配額耗盡
    if not api_data:
        return stats

    # 逐筆比對並 upsert
    for rec in api_data:
        db_rec = api_to_db_record(rec)
        stock_id = db_rec['stock_id']
        date = db_rec['date']

        existing = db.dividend_detail.find_one({'stock_id': stock_id, 'date': date})

        if not existing:
            db.dividend_detail.insert_one(db_rec)
            stats['new'] += 1
        else:
            # 比對關鍵欄位是否有差異（existing 可能含 Decimal128）
            def _to_f(v):
                from bson import Decimal128
                if isinstance(v, Decimal128): return float(v.to_decimal())
                try: return float(v)
                except: return 0.0
            changed = (
                abs(_to_f(existing.get('cash_earnings_distribution', 0)) - db_rec['cash_earnings_distribution']) > 0.001 or
                abs(_to_f(existing.get('stock_earnings_distribution', 0)) - db_rec['stock_earnings_distribution']) > 0.001
            )
            if changed:
                db.dividend_detail.update_one(
                    {'stock_id': stock_id, 'date': date},
                    {'$set': db_rec}
                )
                stats['updated'] += 1
            else:
                stats['unchanged'] += 1

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='強制更新所有股票')
    parser.add_argument('--sym', type=str, help='只更新指定股票')
    parser.add_argument('--limit', type=int, default=500, help='最多更新幾支（預設500）')
    args = parser.parse_args()

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    if args.sym:
        symbols = [args.sym]
        logger.info(f'單一股票模式: {args.sym}')
    else:
        # 找出 stock_factors 有殖利率但 dividend_detail 缺少的股票
        sf_syms = set(db.stock_factors.distinct('symbol', {'dividend_yield': {'$gt': 0}}))
        local_syms = set(db.dividend_detail.distinct('stock_id'))

        if args.all:
            symbols = sorted(sf_syms)
            logger.info(f'強制全量更新: {len(symbols)} 支')
        else:
            missing = sf_syms - local_syms
            # 也加入有本地資料但超過6個月未更新的
            outdated = []
            for sym in (sf_syms & local_syms):
                latest = db.dividend_detail.find_one({'stock_id': sym}, sort=[('date', -1)])
                if latest:
                    try:
                        d = datetime.strptime(latest['date'][:10], '%Y-%m-%d')
                        if datetime.now() - d > timedelta(days=180):
                            outdated.append(sym)
                    except:
                        pass

            symbols = sorted(missing) + sorted(outdated)
            logger.info(f'缺少資料: {len(missing)} 支 | 需更新: {len(outdated)} 支 | 合計: {len(symbols)} 支')

    symbols = symbols[:args.limit]
    logger.info(f'本次處理: {len(symbols)} 支（上限 {args.limit}）')
    logger.info(f'FinMind Token: {TOKEN[:20]}...')

    total = {'new': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0, 'no_data': 0}
    quota_exhausted = False

    for i, sym in enumerate(symbols):
        result = sync_symbol(db, sym, TOKEN, force=args.all)

        if result is None:
            quota_exhausted = True
            logger.warning(f'配額耗盡，已處理 {i}/{len(symbols)} 支，停止')
            break

        if result.get('skipped'):
            total['skipped'] += 1
        elif result['new'] == 0 and result['updated'] == 0 and result['unchanged'] == 0:
            total['no_data'] += 1
        else:
            total['new'] += result['new']
            total['updated'] += result['updated']
            total['unchanged'] += result['unchanged']

        if (i + 1) % 50 == 0:
            logger.info(f'進度: {i+1}/{len(symbols)} | 新增:{total["new"]} 更新:{total["updated"]}')

        time.sleep(0.15)  # 避免 rate limit

    logger.info(f'\n{"="*50}')
    logger.info(f'完成！新增:{total["new"]} 更新:{total["updated"]} 跳過:{total["skipped"]} 無資料:{total["no_data"]}')
    logger.info(f'dividend_detail 總筆數: {db.dividend_detail.count_documents({}):,}')
    logger.info(f'涵蓋股票數: {len(db.dividend_detail.distinct("stock_id"))}')
    if quota_exhausted:
        logger.warning('⚠️  配額耗盡，下次再繼續補充')


if __name__ == '__main__':
    main()
