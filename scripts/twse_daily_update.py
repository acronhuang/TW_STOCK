#!/usr/bin/env python3
"""
TWSE / TPEX 每日股價更新腳本

使用證交所（TWSE）與櫃買中心（TPEX）的免費公開 API，
不需要 FinMind 付費帳號即可每日更新 stock_price 資料。

TWSE API（上市，每交易日 15:30 後有當日資料）:
    https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL

TPEX API（上櫃，當日盤中/收盤後即有資料）:
    https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes

用法:
    # 下載今天的資料（自動偵測最新交易日）
    python3 scripts/twse_daily_update.py

    # 指定日期（格式: YYYY-MM-DD）
    python3 scripts/twse_daily_update.py --date 2026-02-21

    # 試跑（只印出，不寫入 DB）
    python3 scripts/twse_daily_update.py --dry-run

Author: SenVision Team
Date: 2026-02-24
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import urllib3

import requests
import pandas as pd
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

# 抑制 SSL 警告（TWSE 憑證問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / 'src'))


# ── ROC 日期轉換 ────────────────────────────────────────────────────────────────

def _roc_to_date(roc_str: str) -> Optional[datetime]:
    """
    民國年日期字串 → datetime
    '1150224' → datetime(2026, 2, 24)
    '115/02/24' → datetime(2026, 2, 24)
    """
    roc_str = roc_str.strip().replace('/', '')
    if len(roc_str) == 7:   # 1150224
        roc_year  = int(roc_str[:3])
        month     = int(roc_str[3:5])
        day       = int(roc_str[5:7])
    else:
        return None
    year = roc_year + 1911
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _to_dec(val: str) -> Optional[Decimal128]:
    """字串 → Decimal128（去除千分位與空格）"""
    if not val or str(val).strip() in ('', '--', 'N/A', '+', '-'):
        return None
    clean = str(val).replace(',', '').replace('+', '').strip()
    try:
        return Decimal128(str(float(clean)))
    except (ValueError, TypeError):
        return None


# ── TWSE（上市）────────────────────────────────────────────────────────────────

def fetch_twse() -> List[Dict]:
    """
    下載 TWSE 全市場當日收盤行情（上市股票）

    Returns:
        list of dicts with keys: stock_id, date, open, high, low, close, volume,
                                  name, change, transaction, amount, data_source
    """
    url = 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
    r = requests.get(url, timeout=20, verify=False)
    r.raise_for_status()
    raw = r.json()

    records = []
    for row in raw:
        dt = _roc_to_date(row.get('Date', ''))
        if dt is None:
            continue

        stock_id = str(row.get('Code', '')).strip()
        if not stock_id or not stock_id.isdigit():
            continue

        close  = _to_dec(row.get('ClosingPrice'))
        open_  = _to_dec(row.get('OpeningPrice'))
        high   = _to_dec(row.get('HighestPrice'))
        low    = _to_dec(row.get('LowestPrice'))
        vol_str = str(row.get('TradeVolume', '')).replace(',', '').strip()
        volume = _to_dec(vol_str)

        if close is None:
            continue  # 停牌/無成交，略過

        records.append({
            'stock_id':    stock_id,
            'symbol':      stock_id,
            'date':        dt,
            'open':        open_,
            'high':        high,
            'low':         low,
            'close':       close,
            'adj_close':   close,
            'volume':      volume,
            'name':        str(row.get('Name', '')).strip(),
            'change':      row.get('Change'),
            'transaction': row.get('Transaction'),
            'amount':      row.get('TradeValue'),
            'data_source': 'TWSE_OpenAPI',
            'updated_at':  datetime.now(),
        })

    return records


# ── TPEX（上櫃）────────────────────────────────────────────────────────────────

def fetch_tpex() -> List[Dict]:
    """
    下載 TPEX 全市場當日收盤行情（上櫃股票）

    Returns:
        same schema as fetch_twse()
    """
    url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'
    r = requests.get(url, timeout=20, verify=False)
    r.raise_for_status()
    raw = r.json()

    records = []
    for row in raw:
        dt = _roc_to_date(row.get('Date', ''))
        if dt is None:
            continue

        stock_id = str(row.get('SecuritiesCompanyCode', '')).strip()
        if not stock_id or not stock_id.isdigit():
            continue

        close  = _to_dec(row.get('Close'))
        open_  = _to_dec(row.get('Open'))
        high   = _to_dec(row.get('High'))
        low    = _to_dec(row.get('Low'))
        volume = _to_dec(row.get('TradingShares'))

        if close is None:
            continue

        records.append({
            'stock_id':    stock_id,
            'symbol':      stock_id,
            'date':        dt,
            'open':        open_,
            'high':        high,
            'low':         low,
            'close':       close,
            'adj_close':   close,
            'volume':      volume,
            'name':        str(row.get('CompanyName', '')).strip(),
            'change':      row.get('Change'),
            'data_source': 'TPEX_OpenAPI',
            'updated_at':  datetime.now(),
        })

    return records


# ── TWSE 三大法人（T86）─────────────────────────────────────────────────────────

def fetch_twse_institutional(date_str: Optional[str] = None) -> List[Dict]:
    """
    下載 TWSE 三大法人買賣超日報（T86）

    外資、投信、自營商各別及合計的每股淨買超股數。

    Args:
        date_str: 日期字串 YYYY-MM-DD（None=今日）

    Returns:
        list of dicts with keys: stock_id, date, foreign_net, trust_net,
                                  dealer_net, total_net, data_source
    """
    if date_str is None:
        dt_obj = datetime.now()
    else:
        dt_obj = datetime.strptime(date_str, '%Y-%m-%d')

    date_param = dt_obj.strftime('%Y%m%d')
    url = (
        f'https://www.twse.com.tw/rwd/zh/fund/T86'
        f'?response=json&date={date_param}&selectType=ALLBUT0999'
    )

    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    # TWSE 回應後方可能附帶多餘內容，用 raw_decode 只取第一個合法 JSON 物件
    raw, _ = json.JSONDecoder().raw_decode(r.text)

    if raw.get('stat') != 'OK':
        return []

    # 從 response 解析日期（格式：西元年 YYYYMMDD）
    resp_date_str = str(raw.get('date', ''))
    try:
        resp_dt = datetime.strptime(resp_date_str, '%Y%m%d')
    except ValueError:
        resp_dt = dt_obj

    # 欄位索引（固定順序）：
    # 0  證券代號  1  證券名稱
    # 2  外陸資買進  3  外陸資賣出  4  外陸資淨買超
    # 5  投信買進    6  投信賣出    7  投信淨買超
    # 8  自行買賣淨  9  避險淨      10 自營商淨買超
    # 11 三大法人合計淨買超
    records = []
    for row in raw.get('data', []):
        if len(row) < 12:
            continue

        stock_id = str(row[0]).strip()
        if not stock_id or not stock_id.isdigit():
            continue

        records.append({
            'stock_id':    stock_id,
            'date':        resp_dt,
            'foreign_net': _to_dec(row[4]),    # 外陸資淨買超股數
            'trust_net':   _to_dec(row[7]),    # 投信淨買超股數
            'dealer_net':  _to_dec(row[10]),   # 自營商淨買超股數
            'total_net':   _to_dec(row[11]),   # 三大法人合計淨買超股數
            'data_source': 'TWSE_T86',
            'updated_at':  datetime.now(),
        })

    return records


# ── TPEX 三大法人 ────────────────────────────────────────────────────────────────

def fetch_tpex_institutional() -> List[Dict]:
    """
    下載 TPEX 三大法人買賣超日報（上櫃股票）

    使用 TPEX OpenAPI `tpex_3insti_daily_trading`（2026-06 更新，舊端點 tpex_buysell_sec_date
    已失效→302）。需帶瀏覽器 User-Agent，否則被擋轉址。單筆值為「股數」(同 TWSE T86)。

    Returns:
        same schema as fetch_twse_institutional()
    """
    url = 'https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading'
    headers = {'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36')}
    r = requests.get(url, headers=headers, timeout=60, verify=False)
    r.raise_for_status()
    # 端點失效（回傳 HTML/轉址）→ 回空清單
    if 'text/html' in r.headers.get('Content-Type', '') or r.text.lstrip().startswith('<'):
        return []
    try:
        raw = r.json()
    except (json.JSONDecodeError, ValueError):
        return []
    if not raw:
        return []

    def _g(row, *keys):
        for k in keys:
            if k in row:
                return row[k]
        return None

    records = []
    for row in raw:
        dt = _roc_to_date(str(_g(row, 'Date') or ''))
        if dt is None:
            continue
        stock_id = str(_g(row, 'SecuritiesCompanyCode') or '').strip()
        if not stock_id or not stock_id.isdigit():   # 僅普通股(排除 ETF/債如 00679B)
            continue

        # 新欄位：外資及陸資/投信/自營商 各別淨買賣超(Difference)，合計 TotalDifference
        foreign_net = _to_dec(_g(row, 'ForeignInvestorsIncludeMainlandAreaInvestors-Difference',
                                 'ForeignInvestorsInclude MainlandAreaInvestors-Difference'))
        trust_net   = _to_dec(_g(row, 'SecuritiesInvestmentTrustCompanies-Difference'))
        dealer_net  = _to_dec(_g(row, 'Dealers-Difference'))
        total_net   = _to_dec(_g(row, 'TotalDifference'))

        if foreign_net is None and trust_net is None and dealer_net is None:
            continue
        if total_net is None:   # 合計缺則自行加總
            s = sum(float(str(v.to_decimal())) for v in (foreign_net, trust_net, dealer_net) if v is not None)
            total_net = _to_dec(str(s))

        records.append({
            'stock_id':    stock_id,
            'date':        dt,
            'foreign_net': foreign_net,
            'trust_net':   trust_net,
            'dealer_net':  dealer_net,
            'total_net':   total_net,
            'data_source': 'TPEX_3INSTI',
            'updated_at':  datetime.now(),
        })

    return records


# ── TWSE 本益比／殖利率（上市）──────────────────────────────────────────────────

def fetch_twse_peratio() -> List[Dict]:
    """
    下載 TWSE 上市股票本益比、殖利率、股價淨值比

    API: BWIBBU_ALL
    欄位: PEratio, DividendYield, PBratio

    Returns:
        list of dicts: symbol, date, pe_ratio, pb_ratio, dividend_yield, data_source
    """
    url = 'https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL'
    r = requests.get(url, timeout=20, verify=False)
    r.raise_for_status()

    try:
        raw = r.json()
    except (json.JSONDecodeError, ValueError):
        return []

    if not raw:
        return []

    records = []
    for row in raw:
        dt = _roc_to_date(str(row.get('Date', '')))
        if dt is None:
            continue

        symbol = str(row.get('Code', '')).strip()
        if not symbol or not symbol.isdigit():
            continue

        def _to_f(val) -> Optional[float]:
            if not val or str(val).strip() in ('', '--', 'N/A'):
                return None
            try:
                return float(str(val).replace(',', '').strip())
            except (ValueError, TypeError):
                return None

        records.append({
            'symbol':         symbol,
            'date':           dt,
            'pe_ratio':       _to_f(row.get('PEratio')),
            'pb_ratio':       _to_f(row.get('PBratio')),
            'dividend_yield': _to_f(row.get('DividendYield')),
            'data_source':    'TWSE_BWIBBU',
            'updated_at':     datetime.now(),
        })

    return records


# ── TPEX 本益比／殖利率（上櫃）──────────────────────────────────────────────────

def fetch_tpex_peratio() -> List[Dict]:
    """
    下載 TPEX 上櫃股票本益比、殖利率、股價淨值比

    API: tpex_mainboard_peratio_analysis
    欄位: PriceEarningRatio, DividendPerShare, YieldRatio, PriceBookRatio

    Returns:
        list of dicts: symbol, date, pe_ratio, pb_ratio, dividend_yield,
                       dividend_per_share, data_source
    """
    url = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis'
    r = requests.get(url, timeout=20, verify=False)
    r.raise_for_status()

    if 'text/html' in r.headers.get('Content-Type', '') or r.text.lstrip().startswith('<'):
        return []

    try:
        raw = r.json()
    except (json.JSONDecodeError, ValueError):
        return []

    if not raw:
        return []

    records = []
    for row in raw:
        dt = _roc_to_date(str(row.get('Date', '')))
        if dt is None:
            continue

        symbol = str(row.get('SecuritiesCompanyCode', '')).strip()
        if not symbol or not symbol.isdigit():
            continue

        def _to_f(key: str) -> Optional[float]:
            val = row.get(key, '')
            if not val or str(val).strip() in ('', '--', 'N/A'):
                return None
            try:
                return float(str(val).replace(',', '').strip())
            except (ValueError, TypeError):
                return None

        pe  = _to_f('PriceEarningRatio')
        pb  = _to_f('PriceBookRatio')
        div = _to_f('DividendPerShare')
        yld = _to_f('YieldRatio')

        records.append({
            'symbol':             symbol,
            'date':               dt,
            'pe_ratio':           pe,
            'pb_ratio':           pb,
            'dividend_per_share': div,
            'dividend_yield':     yld,
            'data_source':        'TPEX_PERATIO',
            'updated_at':         datetime.now(),
        })

    return records


# ── MongoDB 寫入 ────────────────────────────────────────────────────────────────

def upsert_to_mongo(
    records: List[Dict],
    db,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    批量 upsert（依 stock_id + date 去重）

    Returns:
        (inserted_count, modified_count)
    """
    if not records:
        return 0, 0

    if dry_run:
        print(f"  [DRY RUN] 將寫入 {len(records)} 筆，略過...")
        return 0, 0

    ops = [
        UpdateOne(
            {'stock_id': r['stock_id'], 'date': r['date']},
            {'$set': r},
            upsert=True,
        )
        for r in records
    ]

    result = db.stock_price.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


def upsert_institutional_to_mongo(
    records: List[Dict],
    db,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    批量 upsert 三大法人資料至 institutional_flow 集合
    （依 stock_id + date 去重）
    """
    if not records:
        return 0, 0

    if dry_run:
        print(f"  [DRY RUN] 將寫入 {len(records)} 筆三大法人資料，略過...")
        return 0, 0

    ops = [
        UpdateOne(
            {'stock_id': r['stock_id'], 'date': r['date']},
            {'$set': r},
            upsert=True,
        )
        for r in records
    ]

    result = db.institutional_flow.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


def upsert_tpex_factors_to_mongo(
    records: List[Dict],
    db,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    批量 upsert TPEX PE/PB/殖利率資料至 stock_factors 集合
    （依 symbol + date 去重，只更新 pe_ratio / pb_ratio / dividend_yield 等欄位）
    """
    if not records:
        return 0, 0

    if dry_run:
        print(f"  [DRY RUN] 將寫入 {len(records)} 筆 TPEX 因子資料，略過...")
        return 0, 0

    ops = [
        UpdateOne(
            {'symbol': r['symbol'], 'date': r['date']},
            {'$set': {k: v for k, v in {
                'pe_ratio':           r.get('pe_ratio'),
                'pb_ratio':           r.get('pb_ratio'),
                'dividend_per_share': r.get('dividend_per_share'),
                'dividend_yield':     r.get('dividend_yield'),
                'data_source':        r.get('data_source'),
                'updated_at':         r.get('updated_at'),
            }.items() if v is not None}},
            upsert=True,
        )
        for r in records
    ]

    result = db.stock_factors.bulk_write(ops, ordered=False)
    return result.upserted_count, result.modified_count


# ── 主程式 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='TWSE/TPEX 每日股價更新',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--date', type=str, default=None,
                        help='指定日期（YYYY-MM-DD，預設：今天 API 最新資料）')
    parser.add_argument('--dry-run', action='store_true',
                        help='試跑模式：只印出資料，不寫入 DB')
    parser.add_argument('--db-uri', default='mongodb://localhost:27017/',
                        help='MongoDB URI')
    parser.add_argument('--no-tpex', action='store_true',
                        help='略過 TPEX（只下載上市股票）')
    parser.add_argument('--no-institutional', action='store_true',
                        help='略過三大法人籌碼下載')
    parser.add_argument('--no-peratio', action='store_true',
                        help='略過 TPEX PE/PB 殖利率下載')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  TWSE / TPEX 每日股價 + 籌碼更新")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ── 連接 DB ──────────────────────────────────────────────────
    client = MongoClient(args.db_uri, serverSelectionTimeoutMS=5000)
    db = client['tw_stock_analysis']

    total_new = 0
    total_mod = 0

    # ── TWSE（上市）────────────────────────────────────────────
    print("\n[1/4] 下載 TWSE 上市股票...")
    try:
        twse_records = fetch_twse()
        if twse_records:
            sample_date = twse_records[0]['date'].strftime('%Y-%m-%d')
            print(f"  資料日期: {sample_date}  筆數: {len(twse_records)}")

            # 日期過濾（若指定）
            if args.date:
                target = datetime.strptime(args.date, '%Y-%m-%d')
                twse_records = [r for r in twse_records if r['date'] == target]
                print(f"  過濾後: {len(twse_records)} 筆")

            new_c, mod_c = upsert_to_mongo(twse_records, db, args.dry_run)
            print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
            total_new += new_c
            total_mod += mod_c
        else:
            print("  ⚠️  無資料（可能非交易日）")
    except Exception as e:
        print(f"  ❌ TWSE 下載失敗: {e}")

    # ── TPEX（上櫃）────────────────────────────────────────────
    if not args.no_tpex:
        print("\n[2/4] 下載 TPEX 上櫃股票...")
        try:
            tpex_records = fetch_tpex()
            if tpex_records:
                sample_date = tpex_records[0]['date'].strftime('%Y-%m-%d')
                print(f"  資料日期: {sample_date}  筆數: {len(tpex_records)}")

                if args.date:
                    target = datetime.strptime(args.date, '%Y-%m-%d')
                    tpex_records = [r for r in tpex_records if r['date'] == target]
                    print(f"  過濾後: {len(tpex_records)} 筆")

                new_c, mod_c = upsert_to_mongo(tpex_records, db, args.dry_run)
                print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
                total_new += new_c
                total_mod += mod_c
            else:
                print("  ⚠️  無資料")
        except Exception as e:
            print(f"  ❌ TPEX 下載失敗: {e}")

    # ── 三大法人籌碼 ────────────────────────────────────────────
    if not args.no_institutional:
        print("\n[3/4] 下載三大法人買賣超...")
        inst_new = 0
        inst_mod = 0

        # 使用股價資料的實際交易日（T86 須指定日期才能抓到已收盤資料）
        # twse_records 在此 scope 可能已定義（step 1 成功時）
        inst_date = args.date
        if inst_date is None:
            try:
                inst_date = twse_records[0]['date'].strftime('%Y-%m-%d')
            except Exception:
                pass

        # TWSE T86（上市）
        try:
            twse_inst = fetch_twse_institutional(inst_date)
            if twse_inst:
                sample_date = twse_inst[0]['date'].strftime('%Y-%m-%d')
                print(f"  TWSE 三大法人  日期: {sample_date}  筆數: {len(twse_inst)}")
                new_c, mod_c = upsert_institutional_to_mongo(twse_inst, db, args.dry_run)
                print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
                inst_new += new_c
                inst_mod += mod_c
            else:
                print("  ⚠️  TWSE 三大法人無資料（可能非交易日）")
        except Exception as e:
            print(f"  ❌ TWSE 三大法人下載失敗: {e}")

        # TPEX（上櫃）
        if not args.no_tpex:
            try:
                tpex_inst = fetch_tpex_institutional()
                if tpex_inst:
                    sample_date = tpex_inst[0]['date'].strftime('%Y-%m-%d')
                    print(f"  TPEX 三大法人  日期: {sample_date}  筆數: {len(tpex_inst)}")
                    new_c, mod_c = upsert_institutional_to_mongo(tpex_inst, db, args.dry_run)
                    print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
                    inst_new += new_c
                    inst_mod += mod_c
                else:
                    print("  ⚠️  TPEX 三大法人無資料")
            except Exception as e:
                print(f"  ❌ TPEX 三大法人下載失敗: {e}")

        total_new += inst_new
        total_mod += inst_mod

    # ── PE/PB 殖利率（上市 + 上櫃因子）────────────────────────
    if not args.no_peratio:
        print("\n[4/4] 下載本益比／殖利率（TWSE + TPEX）...")
        per_new = 0
        per_mod = 0

        # TWSE 上市（BWIBBU_ALL）
        try:
            twse_factors = fetch_twse_peratio()
            if twse_factors:
                sample_date = twse_factors[0]['date'].strftime('%Y-%m-%d')
                print(f"  TWSE  日期: {sample_date}  筆數: {len(twse_factors)}")
                new_c, mod_c = upsert_tpex_factors_to_mongo(twse_factors, db, args.dry_run)
                print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
                per_new += new_c
                per_mod += mod_c
            else:
                print("  ⚠️  TWSE PE/PB 無資料")
        except Exception as e:
            print(f"  ❌ TWSE PE/PB 下載失敗: {e}")

        # TPEX 上櫃（tpex_mainboard_peratio_analysis）
        if not args.no_tpex:
            try:
                tpex_factors = fetch_tpex_peratio()
                if tpex_factors:
                    sample_date = tpex_factors[0]['date'].strftime('%Y-%m-%d')
                    print(f"  TPEX  日期: {sample_date}  筆數: {len(tpex_factors)}")
                    new_c, mod_c = upsert_tpex_factors_to_mongo(tpex_factors, db, args.dry_run)
                    print(f"  ✅ 新增: {new_c}  更新: {mod_c}")
                    per_new += new_c
                    per_mod += mod_c
                else:
                    print("  ⚠️  TPEX PE/PB 無資料")
            except Exception as e:
                print(f"  ❌ TPEX PE/PB 下載失敗: {e}")

        total_new += per_new
        total_mod += per_mod

    # ── 摘要 ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  完成！  新增: {total_new}  更新: {total_mod}")
    print(f"{'='*60}\n")

    client.close()


if __name__ == '__main__':
    main()
