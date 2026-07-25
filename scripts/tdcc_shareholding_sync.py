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

判讀 —— 注意：以下直覺**經回測後不成立**，勿據以加分。
  原假設：大戶佔比↑ + 散戶佔比↓ = 主力吸籌（最強）；反之為出貨（見頂）。
  2026-07-17 以 3 年、154 週、約 2000 檔實測（scripts/backtest_holder_conc.py，
  進場設在資料日後第一個週二收盤以避免未來函數）：
    · 純方向（大戶佔比增減）      → 4 週超額 +0.02%，t=0.22   ＝ 無預測力
    · 雙重確認（大戶↑且股東人數↓）→ 4 週超額 +0.23%，t=1.68   ＝ 弱，未達顯著且不耐敏感度檢驗
    · 純幅度（|大戶佔比變化|）    → 4 週超額 +1.00%，t=5.87   ＝ 強，但延後 2 週進場幾乎不衰減
      → 代表它不是事件訊號，而是「活躍波動股」的特徵代理（Q5 成交量為 Q1 的 7 倍、
        年化波動 43% vs 33%），且僅在市場上漲期有效（下跌期價差 +0.03%，t=0.12）。
  結論：本表目前用於人工判讀與圖表（dashboard K線圖大戶子圖），未進入 chip_score_scan
  評分。要接之前請重跑回測 —— 屆時已有更多 TDCC 原生資料，不必倚賴 norway 回補。

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
import time
from datetime import datetime

import requests
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# 重試：本 job 每週只跑一次，且 TDCC id=1-5 **只提供當週**——單次失敗＝該週永久遺失
# （無法事後回補，歷史只能靠 norway_shareholding_backfill.py 一次性補到 2023-03）。
# 故單發請求不可接受，抓 2.3MB 遇網路抖動須退避重試。
RETRIES = 3
RETRY_BACKOFF = 5   # 秒，指數退避基數

BIG_1000 = {'15'}                       # 千張大戶
BIG_400 = {'12', '13', '14', '15'}      # 400 張以上
RETAIL = {'1', '2'}                     # 散戶（<5 張）
TOTAL = '17'


def fetch():
    last = None
    for i in range(RETRIES):
        try:
            r = requests.get(URL, timeout=90, headers=UA)
            r.raise_for_status()
            return r.content.decode('utf-8-sig', 'replace')
        except Exception as e:      # noqa: BLE001 - 連線層各種例外一律退避重試
            last = e
            if i < RETRIES - 1:
                wait = RETRY_BACKOFF * (2 ** i)
                print(f"  ⚠️ 抓取失敗（第 {i+1}/{RETRIES} 次）：{e}｜{wait}s 後重試")
                time.sleep(wait)
    raise RuntimeError(f"TDCC 抓取失敗（已重試 {RETRIES} 次）：{last}")


def _write_heartbeat(db, status: str, stocks: int, ddate):
    """記錄本次同步已執行（system_heartbeat，_id='tdcc_shareholding'），供 watchdog.py 比對。

    每週一次的 job 若靜默停掉，資料面要到下一輪（最長約兩週）才看得出落後；
    心跳讓 watchdog 在當天就能發現「這週二根本沒跑」。"""
    try:
        db.system_heartbeat.update_one(
            {"_id": "tdcc_shareholding"},
            {"$set": {"last_run": datetime.now(), "status": status,
                      "stocks": stocks, "data_date": ddate}},
            upsert=True,
        )
    except Exception as e:          # noqa: BLE001 - 心跳失敗不應讓同步本身失敗
        print(f"  ⚠️ 心跳寫入失敗：{e}")


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
    _write_heartbeat(db, 'ok', len(summary), ddate)


if __name__ == '__main__':
    main()
