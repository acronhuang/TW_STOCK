#!/usr/bin/env python3
"""
TEJ TRAIL 試用版 → MongoDB 全市場同步
========================================
從 TEJ TRAIL 試用帳號下載三大資料集並寫入 MongoDB tw_stock_analysis：

  TRAIL/TATINST1 → institutional_flow (三大法人日買賣超 + 持股比例)
  TRAIL/TAIM1A   → monthly_revenue    (月營收，acc_code=0010)
  TRAIL/TAQFII   → institutional_flow (外資持股比例附加欄位)

試用版限制（自動追蹤）：
  50,000 rows/天，500 calls/天

資料集說明：
  TATINST1 欄位：qfii_buy/sell（外資）、fd_buy/sell（投信）、
                 dlr_buy/sell（自營商）、t_pct（三大法人合計持股%）
  TAIM1A   欄位：acc_code='0010'（本月合計營業收入）、'0020'（累計）
  試用帳號資料延遲：TATINST1 目前只有到 2025-12-31（2026 年資料尚未開放）

回補策略（TATINST1）：
  全市場 1 天 ≈ 2,000 rows
  50K rows/天 ÷ 2,000 rows/天 ≈ 可回補 25 個交易日/天
  2025 全年（~250 交易日）需 約 10 天 完成

Usage:
  python tej_market_sync.py                        # 今日增量（預設）
  python tej_market_sync.py --mode monthly         # 補本月所有交易日
  python tej_market_sync.py --mode history --days 60   # 補最近 60 天
  python tej_market_sync.py --mode backfill        # 自動分批回補（利用每日額度）
  python tej_market_sync.py --datasets inst        # 只同步法人籌碼
  python tej_market_sync.py --datasets rev         # 只同步月營收
  python tej_market_sync.py --check                # 顯示 API 使用量

Author: SenVision Team  Date: 2026-02-25
"""

from __future__ import annotations

import argparse
import logging
import os
import ssl
import sys
import urllib3
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import urllib3
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# ── SSL / HTTPS 修復（解決 macOS Python SSL 憑證問題）──────────────
os.environ['PYTHONHTTPSVERIFY'] = '0'
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
_orig_request = requests.Session.request
def _patch_request(self, *args, **kwargs):
    kwargs['verify'] = False
    return _orig_request(self, *args, **kwargs)
requests.Session.request = _patch_request
# ──────────────────────────────────────────────────────────────────

import tejapi   # noqa: E402  (after SSL patch)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── 設定 ──────────────────────────────────────────────────────────
TEJ_ENV    = '/Users/ming/Desktop/TEJ/.env'
MONGO_URI  = 'mongodb://localhost:27017/'
DB_NAME    = 'tw_stock_analysis'

# 試用版每日限額
DAILY_ROW_LIMIT  = 50_000
DAILY_CALL_LIMIT = 500

# ── MongoDB 集合對應 ──────────────────────────────────────────────
INST_COLL = 'institutional_flow'   # 三大法人
REV_COLL  = 'monthly_revenue'      # 月營收


# ══════════════════════════════════════════════════════════════════
# 初始化
# ══════════════════════════════════════════════════════════════════

def init_tej() -> None:
    """載入 .env 並設定 TEJ API 金鑰"""
    load_dotenv(TEJ_ENV)
    key = os.getenv('TEJ_API_KEY')
    if not key:
        raise RuntimeError(f'找不到 TEJ_API_KEY（檢查 {TEJ_ENV}）')
    tejapi.ApiConfig.api_key   = key
    tejapi.ApiConfig.ignoretz  = True


def get_api_usage() -> Dict:
    """取得今日 API 使用量（rows / calls）"""
    try:
        info = tejapi.ApiConfig.info()
        return {
            'rows_used':  info.get('todayRows', 0),
            'calls_used': info.get('todayReqCount', 0),
            'rows_limit': info.get('rowsDayLimit', DAILY_ROW_LIMIT),
            'calls_limit':info.get('reqDayLimit',  DAILY_CALL_LIMIT),
        }
    except Exception as e:
        logger.warning(f'無法取得 API 使用量: {e}')
        return {'rows_used': 0, 'calls_used': 0,
                'rows_limit': DAILY_ROW_LIMIT, 'calls_limit': DAILY_CALL_LIMIT}


def get_stock_list(db) -> List[str]:
    """從 MongoDB stock_price 取 4 碼普通股清單"""
    try:
        # 取最近有交易的 4 碼股票（排除 ETF/權證等）
        ids = db.stock_price.distinct('stock_id')
        result = sorted(s for s in ids if isinstance(s, str) and s.isdigit() and len(s) == 4)
        logger.info(f'  股票清單：{len(result)} 支（4 碼普通股）')
        return result
    except Exception as e:
        logger.error(f'取得股票清單失敗: {e}')
        return []


# ══════════════════════════════════════════════════════════════════
# 1. 三大法人 TATINST1 → institutional_flow
# ══════════════════════════════════════════════════════════════════

def fetch_institutional(
    date_start: str,
    date_end:   str,
    stock_ids:  Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    下載三大法人買賣超資料。
    若 stock_ids=None 則下載全市場（無 coid 過濾）。
    """
    params = dict(
        mdate={'gte': date_start, 'lte': date_end},
        paginate=True,
        opts={'columns': [
            'coid', 'mdate',
            'qfii_buy', 'qfii_sell',  # 外資
            'fd_buy',   'fd_sell',    # 投信
            'dlr_buy',  'dlr_sell',   # 自營商
            'qfii_p',                 # 外資持股比例
            'fund_p',                 # 投信持股比例
            't_pct',                  # 三大合計持股比例
        ]},
    )
    if stock_ids:
        params['coid'] = stock_ids
    try:
        df = tejapi.get('TRAIL/TATINST1', **params)
        return df
    except Exception as e:
        logger.error(f'TATINST1 下載失敗 ({date_start}~{date_end}): {e}')
        return pd.DataFrame()


def upsert_institutional(df: pd.DataFrame, db) -> Tuple[int, int]:
    """解析 TATINST1 DataFrame 並 upsert 至 MongoDB institutional_flow"""
    if df.empty:
        return 0, 0

    coll = db[INST_COLL]
    coll.create_index(
        [('stock_id', 1), ('date', 1)],
        unique=True, background=True,
    )

    ops = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for _, row in df.iterrows():
        sid  = str(row['coid']).strip()
        date = str(row['mdate'])[:10]  # 只保留 YYYY-MM-DD

        def safe(v):
            try:
                f = float(v)
                return None if f != f else f   # NaN → None
            except (TypeError, ValueError):
                return None

        qfii_buy  = safe(row.get('qfii_buy', 0)) or 0
        qfii_sell = safe(row.get('qfii_sell', 0)) or 0
        fd_buy    = safe(row.get('fd_buy',   0)) or 0
        fd_sell   = safe(row.get('fd_sell',  0)) or 0
        dlr_buy   = safe(row.get('dlr_buy',  0)) or 0
        dlr_sell  = safe(row.get('dlr_sell', 0)) or 0

        foreign_net = round(qfii_buy - qfii_sell, 0)
        trust_net   = round(fd_buy   - fd_sell,   0)
        dealer_net  = round(dlr_buy  - dlr_sell,  0)
        total_net   = round(foreign_net + trust_net + dealer_net, 0)

        ops.append(UpdateOne(
            {'stock_id': sid, 'date': date},
            {'$set': {
                'total_net':    total_net,
                'foreign_net':  foreign_net,
                'trust_net':    trust_net,
                'dealer_net':   dealer_net,
                'foreign_pct':  safe(row.get('qfii_p')),
                'trust_pct':    safe(row.get('fund_p')),
                'total_pct':    safe(row.get('t_pct')),
                'updated_at':   now,
                'data_source':  'TEJ_TATINST1',
            }},
            upsert=True,
        ))

    if not ops:
        return 0, 0
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


# ══════════════════════════════════════════════════════════════════
# 2. 月營收 TAIM1A → monthly_revenue
# ══════════════════════════════════════════════════════════════════

# acc_code 對應表（TEJ 財務科目代碼）
_REVENUE_ACCS = {
    '0010': 'revenue',             # 本月合計營業收入
    '0020': 'cumulative_revenue',  # 本年累計營業收入
}


def fetch_monthly_revenue(
    date_start: str,
    date_end:   str,
    stock_ids:  Optional[List[str]] = None,
) -> pd.DataFrame:
    """下載月營收明細（TAIM1A），只取 acc_code 0010/0020"""
    params = dict(
        mdate={'gte': date_start, 'lte': date_end},
        acc_code=['0010', '0020'],   # 本月 + 累計
        paginate=True,
    )
    if stock_ids:
        params['coid'] = stock_ids
    try:
        df = tejapi.get('TRAIL/TAIM1A', **params)
        return df
    except Exception as e:
        logger.error(f'TAIM1A 下載失敗 ({date_start}~{date_end}): {e}')
        return pd.DataFrame()


def upsert_monthly_revenue(df: pd.DataFrame, db) -> Tuple[int, int]:
    """解析 TAIM1A 並 upsert 至 monthly_revenue（one doc per symbol per month）"""
    if df.empty:
        return 0, 0

    coll = db[REV_COLL]
    coll.create_index(
        [('symbol', 1), ('year_month', 1)],
        unique=True, background=True,
    )

    # 先 pivot：(coid, mdate) → {revenue, cumulative_revenue}
    try:
        pivot = df.pivot_table(
            index=['coid', 'mdate'],
            columns='acc_code',
            values='acc_value',
            aggfunc='first',
        ).reset_index()
        pivot.columns.name = None
    except Exception as e:
        logger.error(f'pivot 失敗: {e}')
        return 0, 0

    # 確保欄位存在
    for code in ('0010', '0020'):
        if code not in pivot.columns:
            pivot[code] = None

    ops = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for _, row in pivot.iterrows():
        sid    = str(row['coid']).strip()
        mdate  = str(row['mdate'])[:10]
        ym     = mdate[:7]   # YYYY-MM

        def safe(v):
            try:
                f = float(v)
                return None if f != f else round(f)
            except (TypeError, ValueError):
                return None

        rev  = safe(row.get('0010'))
        cum  = safe(row.get('0020'))

        if rev is None:
            continue

        ops.append(UpdateOne(
            {'symbol': sid, 'year_month': ym},
            {'$set': {
                'revenue':            rev,
                'cumulative_revenue': cum,
                'updated_at':         now,
                'data_source':        'TEJ_TAIM1A',
            }},
            upsert=True,
        ))

    if not ops:
        return 0, 0
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


# ══════════════════════════════════════════════════════════════════
# 3. 外資持股比例 TAQFII（附加至 institutional_flow）
# ══════════════════════════════════════════════════════════════════

def fetch_qfii(
    date_start: str,
    date_end:   str,
    stock_ids:  Optional[List[str]] = None,
) -> pd.DataFrame:
    """下載外資持股比例（TAQFII）"""
    params = dict(
        mdate={'gte': date_start, 'lte': date_end},
        paginate=True,
        opts={'columns': ['coid', 'mdate', 'ttl_stk', 'inv_pct', 'rem_pct']},
    )
    if stock_ids:
        params['coid'] = stock_ids
    try:
        df = tejapi.get('TRAIL/TAQFII', **params)
        return df
    except Exception as e:
        logger.error(f'TAQFII 下載失敗 ({date_start}~{date_end}): {e}')
        return pd.DataFrame()


def upsert_qfii(df: pd.DataFrame, db) -> Tuple[int, int]:
    """將 TAQFII 外資持股比例合併至 institutional_flow"""
    if df.empty:
        return 0, 0

    coll = db[INST_COLL]
    ops  = []
    now  = datetime.now(timezone.utc).replace(tzinfo=None)

    for _, row in df.iterrows():
        sid  = str(row['coid']).strip()
        date = str(row['mdate'])[:10]

        def safe(v):
            try:
                f = float(v)
                return None if f != f else f
            except (TypeError, ValueError):
                return None

        ops.append(UpdateOne(
            {'stock_id': sid, 'date': date},
            {'$set': {
                'qfii_shares':     safe(row.get('ttl_stk')),   # 外資持股張數
                'qfii_inv_pct':    safe(row.get('inv_pct')),   # 外資持股比例
                'qfii_remain_pct': safe(row.get('rem_pct')),   # 外資可買進比例
                'updated_at':      now,
            }},
            upsert=True,
        ))

    if not ops:
        return 0, 0
    result = coll.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def _last_trading_date() -> str:
    """取前一個工作日日期（簡易版：往前找最多7天）"""
    d = datetime.now()
    for _ in range(7):
        d -= timedelta(days=1)
        if d.weekday() < 5:   # 週一~週五
            return d.strftime('%Y-%m-%d')
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


def sync(
    mode:     str       = 'daily',
    days:     int       = 30,
    datasets: List[str] = None,
    db_uri:   str       = MONGO_URI,
) -> None:
    """
    主同步函式

    Args:
        mode:     'daily' | 'monthly' | 'history'
        days:     歷史回補天數（mode='history' 時使用）
        datasets: ['inst', 'rev', 'qfii'] 的子集；None=全部
        db_uri:   MongoDB URI
    """
    if datasets is None:
        datasets = ['inst', 'rev', 'qfii']

    init_tej()
    client = MongoClient(db_uri)
    db     = client[DB_NAME]

    # ── 日期範圍 ──────────────────────────────────────────────────
    today = datetime.now().strftime('%Y-%m-%d')
    if mode == 'daily':
        last = _last_trading_date()
        date_start, date_end = last, today
        label = f'今日增量 ({last})'
    elif mode == 'monthly':
        date_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        date_end   = today
        label = f'本月 ({date_start} ~ {date_end})'
    elif mode == 'history':
        date_start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        date_end   = today
        label = f'歷史 {days} 天 ({date_start} ~ {date_end})'
    else:
        raise ValueError(f'未知 mode: {mode}')

    # ── API 使用量檢查 ────────────────────────────────────────────
    usage = get_api_usage()
    rows_remaining = usage['rows_limit'] - usage['rows_used']
    logger.info(f'TEJ API：今日已用 {usage["rows_used"]:,} rows / {usage["rows_limit"]:,}  '
                f'（剩餘 {rows_remaining:,} rows）')

    if rows_remaining < 2000:
        logger.warning('今日 API 額度不足（< 2,000 rows），跳過')
        return

    # ── 取得股票清單 ──────────────────────────────────────────────
    stock_ids = get_stock_list(db)
    if not stock_ids:
        logger.error('無法取得股票清單，退出')
        return

    logger.info(f'\n同步模式：{label}  資料集：{", ".join(datasets)}')
    logger.info(f'股票數：{len(stock_ids)} 支')
    total_new = total_mod = 0

    # ── 1. 三大法人籌碼 ───────────────────────────────────────────
    if 'inst' in datasets:
        logger.info('\n[1/3] 下載三大法人買賣超（TATINST1）...')
        # 全市場一次查詢（不傳 coid）→ 一個 API call 取所有股票
        df_inst = fetch_institutional(date_start, date_end, stock_ids=None)
        if not df_inst.empty:
            logger.info(f'  取得 {len(df_inst):,} 筆  ({df_inst["coid"].nunique():,} 支股票)')
            n, m = upsert_institutional(df_inst, db)
            total_new += n; total_mod += m
            logger.info(f'  ✅ 新增 {n}，更新 {m}')
        else:
            logger.warning('  ⚠️  TATINST1 無資料（可能為非交易日或試用版資料延遲）')

    # ── 2. 月營收 ─────────────────────────────────────────────────
    if 'rev' in datasets:
        logger.info('\n[2/3] 下載月營收（TAIM1A）...')
        # 月營收按月發布，調整 date_start 到月初
        rev_start = date_start[:7] + '-01'
        df_rev = fetch_monthly_revenue(rev_start, date_end, stock_ids=None)
        if not df_rev.empty:
            logger.info(f'  取得 {len(df_rev):,} 筆  ({df_rev["coid"].nunique():,} 支股票)')
            n, m = upsert_monthly_revenue(df_rev, db)
            total_new += n; total_mod += m
            logger.info(f'  ✅ 新增 {n}，更新 {m}')
        else:
            logger.warning('  ⚠️  TAIM1A 無資料')

    # ── 3. 外資持股比例 ───────────────────────────────────────────
    if 'qfii' in datasets:
        logger.info('\n[3/3] 下載外資持股比例（TAQFII）...')
        df_qfii = fetch_qfii(date_start, date_end, stock_ids=None)
        if not df_qfii.empty:
            logger.info(f'  取得 {len(df_qfii):,} 筆  ({df_qfii["coid"].nunique():,} 支股票)')
            n, m = upsert_qfii(df_qfii, db)
            total_new += n; total_mod += m
            logger.info(f'  ✅ 新增 {n}，更新 {m}')
        else:
            logger.warning('  ⚠️  TAQFII 無資料')

    # ── 完成統計 ──────────────────────────────────────────────────
    logger.info(f'\n✅ 同步完成：新增 {total_new}，更新 {total_mod} 筆')

    # 更新後 API 使用量
    usage2 = get_api_usage()
    rows_delta = usage2['rows_used'] - usage['rows_used']
    logger.info(f'   本次消耗：{rows_delta:,} rows  '
                f'（今日累計：{usage2["rows_used"]:,} / {usage2["rows_limit"]:,}）')

    # ── 最新法人籌碼統計 ──────────────────────────────────────────
    try:
        cnt = db[INST_COLL].estimated_document_count()
        latest = db[INST_COLL].find_one({}, sort=[('date', -1)], projection={'date': 1, '_id': 0})
        d = latest['date'] if latest else '-'
        logger.info(f'   institutional_flow：{cnt:,} 筆，最新 {d}')
    except Exception:
        pass

    client.close()


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='TEJ TRAIL → MongoDB 全市場同步')
    parser.add_argument('--mode', choices=['daily', 'monthly', 'history'],
                        default='daily',
                        help='同步模式（預設: daily）')
    parser.add_argument('--days', type=int, default=30,
                        help='歷史回補天數（--mode history 時使用，預設 30）')
    parser.add_argument('--datasets', nargs='+',
                        choices=['inst', 'rev', 'qfii'],
                        default=None,
                        help='指定要同步的資料集（預設全部）')
    parser.add_argument('--check', action='store_true',
                        help='只顯示 API 使用量，不執行下載')
    parser.add_argument('--db-uri', default=MONGO_URI,
                        help='MongoDB URI')

    args = parser.parse_args()

    init_tej()

    if args.check:
        usage = get_api_usage()
        print(f'\n=== TEJ API 使用量 ===')
        print(f'  今日 rows:  {usage["rows_used"]:>8,} / {usage["rows_limit"]:,}')
        print(f'  今日 calls: {usage["calls_used"]:>8,} / {usage["calls_limit"]:,}')
        print(f'  剩餘 rows:  {usage["rows_limit"] - usage["rows_used"]:>8,}')
        return

    sync(
        mode=args.mode,
        days=args.days,
        datasets=args.datasets,
        db_uri=args.db_uri,
    )


if __name__ == '__main__':
    main()
