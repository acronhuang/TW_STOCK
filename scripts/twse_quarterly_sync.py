#!/usr/bin/env python3
"""
TWSE / TPEX 季報即時同步
=========================
從 TWSE OpenAPI（t187ap14_L）和 TPEX OpenAPI（mopsfin_t187ap14_O）
下載每季已申報的財報資料，自動存入 MongoDB quarterly_earnings。

特點：
  - 無速率限制（官方 OpenAPI，免費）
  - 申報季期間（每季末後 45 天內）每天呼叫一次即可收集完所有公司
  - 資料涵蓋上市 + 上櫃共 ~2,000 支
  - 欄位：EPS、營業收入、營業利益、稅後淨利
  - 搭配 daily_senvision.sh 每日自動執行

Filing schedule（台灣):
  Q1 (截止 5/15): 4月中 ～ 5月15日
  Q2 (截止 8/14): 7月中 ～ 8月14日
  Q3 (截止 11/14): 10月中 ～ 11月14日
  Q4/年報 (截止 3/31): 2月中 ～ 3月31日

Usage:
  python twse_quarterly_sync.py           # 同步目前申報中的季度
  python twse_quarterly_sync.py --verbose # 顯示詳細輸出
"""

import sys
import logging
import argparse
from datetime import datetime, timezone
from typing import Optional

import requests
import urllib3
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

MONGO_URI = 'mongodb://localhost:27017/'
DB_NAME   = 'tw_stock_analysis'
COLL_NAME = 'quarterly_earnings'

TWSE_URL = 'https://openapi.twse.com.tw/v1/opendata/t187ap14_L'
TPEX_URL = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O'

HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}


# ── 解析工具 ──────────────────────────────────────────────────────────────
def safe_float(s: str) -> Optional[float]:
    try:
        return float(str(s).replace(',', '').strip())
    except (ValueError, TypeError):
        return None


def parse_twse_row(row: dict) -> Optional[dict]:
    """
    TWSE t187ap14_L 單筆 → 標準化 dict。
    欄位：出表日期, 年度(ROC), 季別, 公司代號, 基本每股盈餘(元),
          營業收入, 營業利益, 稅後淨利
    """
    try:
        year_ce  = int(row['年度']) + 1911
        season   = int(row['季別'])
        symbol   = str(row['公司代號']).strip()
        rev      = safe_float(row.get('營業收入', ''))
        op_inc   = safe_float(row.get('營業利益', ''))
        net_inc  = safe_float(row.get('稅後淨利', ''))
        eps      = safe_float(row.get('基本每股盈餘(元)', ''))
    except (KeyError, ValueError):
        return None

    income: dict = {
        'revenue':          rev,
        'operating_income': op_inc,
        'net_income':       net_inc,
        'eps':              eps,
        # 計算利潤率
        'operating_margin': round(op_inc / rev * 100, 2) if rev and op_inc and rev != 0 else None,
        'net_margin':       round(net_inc / rev * 100, 2) if rev and net_inc and rev != 0 else None,
    }
    return {
        'symbol':      symbol,
        'year':        year_ce,
        'season':      season,
        'income':      income,
        'balance':     {},
        'cashflow':    {},
        'report_type': '合併',
        'data_source': 'TWSE_OpenAPI',
        'updated_at':  datetime.now(timezone.utc).replace(tzinfo=None),
    }


def parse_tpex_row(row: dict) -> Optional[dict]:
    """
    TPEX mopsfin_t187ap14_O 單筆 → 標準化 dict。
    欄位：Year(ROC), 季別, SecuritiesCompanyCode,
          基本每股盈餘, 營業收入, 營業利益, 稅後淨利
    """
    try:
        year_ce  = int(row['Year']) + 1911
        season   = int(row['季別'])
        symbol   = str(row.get('SecuritiesCompanyCode', '')).strip()
        rev      = safe_float(row.get('營業收入', ''))
        op_inc   = safe_float(row.get('營業利益', ''))
        net_inc  = safe_float(row.get('稅後淨利', ''))
        eps      = safe_float(row.get('基本每股盈餘', ''))
    except (KeyError, ValueError):
        return None

    income: dict = {
        'revenue':          rev,
        'operating_income': op_inc,
        'net_income':       net_inc,
        'eps':              eps,
        'operating_margin': round(op_inc / rev * 100, 2) if rev and op_inc and rev != 0 else None,
        'net_margin':       round(net_inc / rev * 100, 2) if rev and net_inc and rev != 0 else None,
    }
    return {
        'symbol':      symbol,
        'year':        year_ce,
        'season':      season,
        'income':      income,
        'balance':     {},
        'cashflow':    {},
        'report_type': '合併',
        'data_source': 'TPEX_OpenAPI',
        'updated_at':  datetime.now(timezone.utc).replace(tzinfo=None),
    }


def fetch_json(url: str, session: requests.Session) -> list:
    try:
        r = session.get(url, timeout=20, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error(f"取得 {url} 失敗: {exc}")
        return []


_MONEY = ['revenue', 'operating_income', 'net_income']


def normalize_income(doc: dict, coll) -> dict:
    """TWSE/TPEX t187ap14 金額為『千元 + 累計(YTD)』→ 轉成『元 + 單季』(與 FinMind 一致)。
    季別1：累計=單季，僅 ×1000；季別>1：×1000 後減同年前面各季單季(DB)。
    無法湊齊前面季者 → 金額設 None(不存錯數)。margins 以單季重算。EPS 同步反累計。"""
    inc = doc['income']
    season, year, sym = doc['season'], doc['year'], doc['symbol']
    for k in _MONEY:
        if inc.get(k) is not None:
            inc[k] = float(inc[k]) * 1000.0
    if season > 1:
        prior = {k: 0.0 for k in _MONEY}
        eps_prior = 0.0
        have = 0
        for s in range(1, season):
            d = coll.find_one({'symbol': sym, 'year': year, 'season': s})
            pinc = d.get('income', {}) if d else {}
            if d and pinc.get('revenue') is not None:
                have += 1
                for k in _MONEY:
                    prior[k] += float(pinc.get(k) or 0)
                eps_prior += float(pinc.get('eps') or 0)
        if have == season - 1:
            for k in _MONEY:
                if inc.get(k) is not None:
                    inc[k] = round(inc[k] - prior[k])
            if inc.get('eps') is not None:
                inc['eps'] = round(float(inc['eps']) - eps_prior, 2)
        else:
            for k in _MONEY:
                inc[k] = None
    rev, oi, ni = inc.get('revenue'), inc.get('operating_income'), inc.get('net_income')
    inc['operating_margin'] = round(oi / rev * 100, 2) if rev and oi is not None else None
    inc['net_margin'] = round(ni / rev * 100, 2) if rev and ni is not None else None
    inc['unit_fixed'] = True
    return doc


def sync(verbose: bool = False):
    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]
    coll   = db[COLL_NAME]
    coll.create_index(
        [('symbol', 1), ('year', 1), ('season', 1)],
        unique=True, background=True,
    )

    session = requests.Session()
    session.headers.update(HEADERS)

    ops = []
    stats = {'twse': 0, 'tpex': 0, 'skip': 0}

    # ── TWSE ─────────────────────────────────────────────────────────────
    twse_data = fetch_json(TWSE_URL, session)
    logger.info(f"TWSE t187ap14_L: {len(twse_data)} 筆")
    for row in twse_data:
        doc = parse_twse_row(row)
        if not doc:
            stats['skip'] += 1
            continue
        normalize_income(doc, coll)
        ops.append(UpdateOne(
            {'symbol': doc['symbol'], 'year': doc['year'], 'season': doc['season']},
            {'$setOnInsert': {
                 'balance':     {},
                 'cashflow':    {},
                 'report_type': '合併',
                 'data_source': 'TWSE_OpenAPI',
             },
             '$set': {
                 'income':     doc['income'],
                 'updated_at': doc['updated_at'],
             }},
            upsert=True,
        ))
        stats['twse'] += 1
        if verbose:
            inc = doc['income']
            logger.info(
                f"  {doc['symbol']} {doc['year']}Q{doc['season']}  "
                f"EPS={inc.get('eps')}  Rev={(inc.get('revenue') or 0):,.0f}"
            )

    # ── TPEX ─────────────────────────────────────────────────────────────
    tpex_data = fetch_json(TPEX_URL, session)
    logger.info(f"TPEX mopsfin_t187ap14_O: {len(tpex_data)} 筆")
    for row in tpex_data:
        doc = parse_tpex_row(row)
        if not doc:
            stats['skip'] += 1
            continue
        normalize_income(doc, coll)
        ops.append(UpdateOne(
            {'symbol': doc['symbol'], 'year': doc['year'], 'season': doc['season']},
            {'$setOnInsert': {
                 'balance':     {},
                 'cashflow':    {},
                 'report_type': '合併',
                 'data_source': 'TPEX_OpenAPI',
             },
             '$set': {
                 'income':     doc['income'],
                 'updated_at': doc['updated_at'],
             }},
            upsert=True,
        ))
        stats['tpex'] += 1

    # ── 寫入 MongoDB ──────────────────────────────────────────────────────
    if ops:
        result = coll.bulk_write(ops, ordered=False)
        inserted = result.upserted_count
        modified = result.modified_count
        logger.info(
            f"✅ 寫入完成：TWSE {stats['twse']} + TPEX {stats['tpex']} 筆  "
            f"(新增 {inserted}，更新 {modified})"
        )
    else:
        logger.info("無新資料")

    # 印出本次最新季度統計
    agg = list(coll.aggregate([
        {'$group': {'_id': {'year': '$year', 'season': '$season'},
                    'count': {'$sum': 1}}},
        {'$sort':  {'_id.year': -1, '_id.season': -1}},
        {'$limit': 4},
    ]))
    logger.info("最近幾季累積筆數：")
    for r in agg:
        logger.info(f"  {r['_id']['year']}Q{r['_id']['season']}: {r['count']:,} 支")


def main():
    parser = argparse.ArgumentParser(description='TWSE/TPEX 季報即時同步')
    parser.add_argument('--verbose', action='store_true', help='顯示每支股票明細')
    args = parser.parse_args()
    sync(verbose=args.verbose)


if __name__ == '__main__':
    main()
