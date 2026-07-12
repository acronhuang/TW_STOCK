#!/usr/bin/env python3
"""
外資及陸資持股比例同步（TWSE，免費、每日、全市場）
==================================================
來源：TWSE 外資及陸資投資持股統計 MI_QFIIS
      https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&date=YYYYMMDD&selectType=ALLBUT0999
      每個交易日一次，約 1349 檔上市股（免費，不吃 FinMind 額度）。

為何自建而非用 FinMind：FinMind 免費版 `TaiwanStockShareholding` 僅能單檔查（帶 data_id），
全市場查詢被鎖需付費；TWSE MI_QFIIS 直接給全市場，免費。（同集保大戶走 TDCC 的策略。）

存進 foreign_holding：
  foreign_ratio  全體外資及陸資持股比率(%)  ← 核心：近 N 日上升 = 外資持續吸籌（累積水位，與每日 foreign_net 流量互補）
  remain_ratio   外資及陸資尚可投資比率(%)   （越低=越接近上限，外資想加也難）

用法：
    python3 scripts/twse_foreign_holding_sync.py            # 抓最新交易日
    python3 scripts/twse_foreign_holding_sync.py --days 6   # 回補近 6 個交易日（首次 bootstrap 趨勢）
    python3 scripts/twse_foreign_holding_sync.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

URL = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&date={date}&selectType=ALLBUT0999"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
FOREIGN_RATIO_IDX = 7   # 全體外資及陸資持股比率
REMAIN_RATIO_IDX = 6    # 外資及陸資尚可投資比率


def _num(s):
    try:
        return float(str(s).replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def fetch_day(d: datetime):
    """抓某日 MI_QFIIS，回 list[dict]；非交易日（0 筆）回 []。"""
    r = requests.get(URL.format(date=d.strftime('%Y%m%d')), timeout=60, headers=UA)
    r.raise_for_status()
    data = r.json().get('data', []) or []
    out = []
    for row in data:
        if len(row) <= FOREIGN_RATIO_IDX:
            continue
        sym = str(row[0]).strip()
        fr = _num(row[FOREIGN_RATIO_IDX])
        if not sym or fr is None:
            continue
        out.append({'date': d.replace(hour=0, minute=0, second=0, microsecond=0),
                    'stock_id': sym, 'name': str(row[1]).strip(),
                    'foreign_ratio': fr, 'remain_ratio': _num(row[REMAIN_RATIO_IDX])})
    return out


def main():
    ap = argparse.ArgumentParser(description="外資及陸資持股比例同步（TWSE）")
    ap.add_argument('--days', type=int, default=1, help='回補近 N 個交易日（含最新）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--db-uri', default=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    args = ap.parse_args()

    db = None if args.dry_run else MongoClient(args.db_uri)['tw_stock_analysis']
    if db is not None:
        db.foreign_holding.create_index([('stock_id', ASCENDING), ('date', DESCENDING)], unique=True)

    got = 0
    probe = datetime.now()
    tries = 0
    while got < args.days and tries < args.days + 12:   # 往回找交易日（跳過假日）
        tries += 1
        try:
            rows = fetch_day(probe)
        except Exception as e:
            print(f"  {probe:%Y-%m-%d} 抓取失敗: {e}")
            rows = []
        if rows:
            got += 1
            print(f"[{probe:%Y-%m-%d}] {len(rows)} 檔外資持股")
            if db is not None:
                ops = [UpdateOne({'stock_id': r['stock_id'], 'date': r['date']},
                                 {'$set': {**r, 'data_source': 'TWSE_MI_QFIIS',
                                           'updated_at': datetime.now()}}, upsert=True)
                       for r in rows]
                res = db.foreign_holding.bulk_write(ops, ordered=False)
                print(f"   寫入 upsert {res.upserted_count} / 更新 {res.modified_count}")
            # 抽樣
            for r in rows[:1]:
                print(f"   例：{r['stock_id']} {r['name']} 外資 {r['foreign_ratio']}% 尚可 {r['remain_ratio']}%")
            time.sleep(1.2)          # 禮貌性節流
        probe -= timedelta(days=1)

    if args.dry_run:
        print("[DRY-RUN] 未寫入")
    print(f"完成：共 {got} 個交易日")


if __name__ == '__main__':
    main()
