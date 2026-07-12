#!/usr/bin/env python3
"""
集保戶股權分散表同步（TDCC 開放資料，免費、每週）
==================================================
來源：集保結算所 https://opendata.tdcc.com.tw/getOD.ashx?id=1-5
      全市場、每週一次（資料日通常為上週五），約 2.3MB / 6.8 萬列。

持股分級（級距，單位=股，1 張 = 1000 股）：
  級 1     1–999 股（零股/最小散戶）
  級 2     1,000–5,000（≈1–5 張）
  級12–14  400,001–1,000,000（40–100 萬股，中大戶）
  級15     1,000,001 股以上（>1000 張＝**千張大戶**）← 主力/法人/政府基金
  級17     合計

每檔彙整為一筆存進 shareholding：
  big_pct     千張大戶（級15）佔集保庫存比例  ← 核心：週增=大戶吸籌、週減=大戶出貨
  big_holders 千張大戶人數
  big400_pct  400 張以上（級12–15）佔比
  retail_pct  散戶（級1–2，<5 張）佔比
  total_holders 總股東數（級17 人數）

判讀（與 chip_score_scan 的法人/融資互補）：
  大戶佔比↑ + 散戶佔比↓ = 籌碼集中、主力吸籌（最強）
  大戶佔比↓ + 散戶佔比↑ = 籌碼渙散、主力出貨給散戶（見頂）

用法：
    python3 scripts/tdcc_shareholding_sync.py            # 抓最新週 + 寫入
    python3 scripts/tdcc_shareholding_sync.py --dry-run  # 只解析不寫入
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

BIG_1000 = {'15'}                       # 千張大戶
BIG_400 = {'12', '13', '14', '15'}      # 400 張以上
RETAIL = {'1', '2'}                     # 散戶（<5 張）
TOTAL = '17'


def fetch():
    r = requests.get(URL, timeout=90, headers=UA)
    r.raise_for_status()
    return r.content.decode('utf-8-sig', 'replace')


def parse(text):
    """回傳 (data_date: datetime, {stock_id: summary})。"""
    rows = list(csv.reader(io.StringIO(text)))
    agg = {}          # stock_id -> {level: (holders, shares, pct)}
    ddate = None
    for r in rows[1:]:
        if len(r) < 6:
            continue
        ddate = ddate or r[0].strip()
        sym = r[1].strip()
        lvl = r[2].strip()
        try:
            holders, shares, pct = int(r[3]), int(r[4]), float(r[5])
        except ValueError:
            continue
        agg.setdefault(sym, {})[lvl] = (holders, shares, pct)

    d = datetime.strptime(ddate, '%Y%m%d')
    out = {}
    for sym, lv in agg.items():
        def pct_sum(levels):
            return round(sum(lv.get(x, (0, 0, 0))[2] for x in levels), 2)
        out[sym] = {
            'big_pct': pct_sum(BIG_1000),
            'big_holders': lv.get('15', (0, 0, 0))[0],
            'big400_pct': pct_sum(BIG_400),
            'retail_pct': pct_sum(RETAIL),
            'total_holders': lv.get(TOTAL, (0, 0, 0))[0],
        }
    return d, out


def main():
    ap = argparse.ArgumentParser(description="集保戶股權分散表同步（TDCC）")
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--db-uri', default=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    args = ap.parse_args()

    print(f"抓取 TDCC 股權分散表 … {datetime.now():%F %T}")
    text = fetch()
    ddate, summary = parse(text)
    print(f"資料日 {ddate:%Y-%m-%d}｜解析 {len(summary)} 檔")
    # 抽樣顯示
    for s in ('2330', '2317', '2454'):
        if s in summary:
            x = summary[s]
            print(f"  {s}: 千張大戶 {x['big_pct']}%（{x['big_holders']}人）"
                  f" 400張+ {x['big400_pct']}% 散戶 {x['retail_pct']}%")

    if args.dry_run:
        print("[DRY-RUN] 未寫入"); return

    db = MongoClient(args.db_uri)['tw_stock_analysis']
    col = db.shareholding
    col.create_index([('stock_id', ASCENDING), ('date', DESCENDING)], unique=True)
    ops = []
    for sym, x in summary.items():
        doc = {'date': ddate, 'stock_id': sym, 'data_source': 'TDCC', 'updated_at': datetime.now(), **x}
        ops.append(UpdateOne({'stock_id': sym, 'date': ddate}, {'$set': doc}, upsert=True))
    if ops:
        res = col.bulk_write(ops, ordered=False)
        print(f"✅ 寫入 shareholding：upsert {res.upserted_count} / 更新 {res.modified_count}"
              f"（共 {len(ops)} 檔 @ {ddate:%Y-%m-%d}）")


if __name__ == '__main__':
    main()
