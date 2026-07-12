#!/usr/bin/env python3
"""
回補 stock_price 缺口日期

使用 TWSE MI_INDEX + TPEX 報表端點取得指定日期的全市場行情。
"""
import sys, time, json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import requests
import urllib3
from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def _to_dec(val) -> Optional[Decimal128]:
    if not val or str(val).strip() in ('', '--', 'N/A', '+', '-', '---'):
        return None
    clean = str(val).replace(',', '').replace('+', '').strip()
    try:
        f = float(clean)
        if f == 0:
            return None
        return Decimal128(str(f))
    except (ValueError, TypeError):
        return None


def fetch_twse_by_date(date_str: str) -> List[Dict]:
    """
    用 MI_INDEX 抓指定日期的 TWSE 全市場行情
    date_str: YYYYMMDD
    """
    url = (
        f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
        f'?response=json&date={date_str}&type=ALLBUT0999'
    )
    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    raw = r.json()

    if raw.get('stat') != 'OK':
        return []

    # tables[8] 通常是個股日成交資訊
    tables = raw.get('tables', [])
    data_table = None
    for t in tables:
        title = t.get('title', '')
        if '個股' in title and '日成交' in title:
            data_table = t
            break
    if not data_table:
        # fallback: 找最大的 table
        data_table = max(tables, key=lambda t: len(t.get('data', [])), default=None)

    if not data_table or not data_table.get('data'):
        return []

    dt = datetime.strptime(date_str, '%Y%m%d')
    records = []
    for row in data_table['data']:
        if len(row) < 10:
            continue
        stock_id = str(row[0]).strip()
        if not stock_id.isdigit():
            continue

        # MI_INDEX 欄位順序:
        # 0=證券代號 1=證券名稱 2=成交股數 3=成交筆數 4=成交金額
        # 5=開盤價 6=最高價 7=最低價 8=收盤價 9=漲跌(+/-) 10=漲跌價差
        # 11=最後揭示買價 12=最後揭示買量 13=最後揭示賣價 14=最後揭示賣量
        # 15=本益比
        close = _to_dec(row[8])
        if close is None:
            continue

        records.append({
            'stock_id': stock_id,
            'symbol': stock_id,
            'date': dt,
            'open': _to_dec(row[5]),
            'high': _to_dec(row[6]),
            'low': _to_dec(row[7]),
            'close': close,
            'adj_close': close,
            'volume': _to_dec(row[2]),
            'name': str(row[1]).strip(),
            'data_source': 'TWSE_MI_INDEX',
            'updated_at': datetime.now(),
        })

    return records


def fetch_tpex_by_date(date_str: str) -> List[Dict]:
    """
    用 TPEX 報表抓指定日期上櫃行情
    date_str: YYYYMMDD → 轉成民國年 YYY/MM/DD
    """
    dt = datetime.strptime(date_str, '%Y%m%d')
    roc_date = f'{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}'

    url = (
        f'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php'
        f'?l=zh-tw&d={roc_date}&se=EW&_=1'
    )
    r = requests.get(url, timeout=30, verify=False)
    r.raise_for_status()
    raw = r.json()

    aa_data = raw.get('aaData', [])
    if not aa_data:
        return []

    records = []
    for row in aa_data:
        if len(row) < 10:
            continue
        stock_id = str(row[0]).strip()
        if not stock_id.isdigit():
            continue

        # TPEX 欄位: 0=代號 1=名稱 2=收盤 3=漲跌 4=開盤 5=最高 6=最低
        # 7=均價 8=成交股數 9=成交金額 10=成交筆數 ...
        close = _to_dec(row[2])
        if close is None:
            continue

        records.append({
            'stock_id': stock_id,
            'symbol': stock_id,
            'date': dt,
            'open': _to_dec(row[4]),
            'high': _to_dec(row[5]),
            'low': _to_dec(row[6]),
            'close': close,
            'adj_close': close,
            'volume': _to_dec(row[8]),
            'name': str(row[1]).strip(),
            'data_source': 'TPEX_OTC',
            'updated_at': datetime.now(),
        })

    return records


def upsert_records(records, db):
    if not records:
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


def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']

    # 找出 2/26 ~ 今天之間缺少的交易日
    # 先列出所有應有的交易日（週一~五）
    start = datetime(2026, 2, 27)
    end = datetime(2026, 3, 9)

    # 已有的日期
    existing = set(
        d.strftime('%Y%m%d')
        for d in db.stock_price.distinct('date', {
            'date': {'$gte': start, '$lte': end}
        })
    )

    # 產生候選交易日（排除週末）
    candidates = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri
            ds = d.strftime('%Y%m%d')
            # 如果該日期缺少或記錄數不足（不完整）
            count = db.stock_price.count_documents({'date': d})
            if count < 3000:  # 正常應有 ~7000 筆
                candidates.append((ds, count))
        d += timedelta(days=1)

    if not candidates:
        print("沒有需要回補的日期")
        return

    print(f"需要回補的日期: {len(candidates)} 天")
    for ds, cnt in candidates:
        print(f"  {ds} (現有 {cnt} 筆)")

    total_new, total_mod = 0, 0

    for ds, existing_count in candidates:
        print(f"\n--- 回補 {ds} ---")

        # TWSE
        try:
            twse = fetch_twse_by_date(ds)
            if twse:
                new, mod = upsert_records(twse, db)
                print(f"  TWSE: {len(twse)} 筆 (新增 {new}, 更新 {mod})")
                total_new += new
                total_mod += mod
            else:
                print(f"  TWSE: 無資料（可能為假日）")
        except Exception as e:
            print(f"  TWSE 失敗: {e}")

        time.sleep(3)  # 避免被擋

        # TPEX
        try:
            tpex = fetch_tpex_by_date(ds)
            if tpex:
                new, mod = upsert_records(tpex, db)
                print(f"  TPEX: {len(tpex)} 筆 (新增 {new}, 更新 {mod})")
                total_new += new
                total_mod += mod
            else:
                print(f"  TPEX: 無資料")
        except Exception as e:
            print(f"  TPEX 失敗: {e}")

        time.sleep(3)

    print(f"\n=== 回補完成 ===")
    print(f"總新增: {total_new}  總更新: {total_mod}")

    client.close()


if __name__ == '__main__':
    main()
