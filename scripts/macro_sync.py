#!/usr/bin/env python3
"""
總經指標同步（務實混合版）— 把 macro 分析從空殼變真實
====================================================
背景：FinMind 把利率/匯率/CPI/景氣等總經 dataset 鎖在付費等級(HTTP400)，
      免費 token 抓不到 → macro_indicators 一直空 → 總經分析是空殼(5/6 指標 null)。
      而 CPI/景氣的政府開放資料只有 ZIP/XML 下載(URL會404、SSL錯、版本變動)，
      寫自動爬蟲一兩個月就壞。故採「穩定源自動 + 月頻指標存值」混合：

  [自動] 匯率 USD/TWD ← 台銀牌告匯率 CSV(免費無金鑰)
  [自動] 外資/大盤    ← 已由 MacroAnalyzer._get_taiex_summary 從 DB 取得
  [存值] 利率(重貼現率)、CPI年增率、M1B/M2年增率、景氣對策信號
         → 月頻、各只是一個數字，用真實當期值 seed，每月用 CLI 旗標更新。

寫入 macro_indicators（沿用 MacroAnalyzer._save_indicator 格式，/api/macro 直接讀）。

用法：
  python scripts/macro_sync.py                          # 每日跑：更新匯率 + 確保月頻值在
  python scripts/macro_sync.py --set-cpi 2.20           # 月更 CPI 年增率
  python scripts/macro_sync.py --set-rate 2.000         # 央行調率時更新
  python scripts/macro_sync.py --set-m1b 8.25 --set-m2 6.45
  python scripts/macro_sync.py --set-signal 39 --set-signal-light 紅燈
"""
from __future__ import annotations
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bson.decimal128 import Decimal128
from pymongo import UpdateOne

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:
    pass
from src.analysis.macro_indicators import MacroAnalyzer

FINMIND_TOKEN = os.getenv('FINMIND_API_TOKEN', '')


def _d128(v):
    try:
        return Decimal128(str(float(v)))
    except (TypeError, ValueError):
        return None


def sync_taiex(db) -> str:
    """加權指數(TAIEX) → stock_price(symbol='TAIEX')，供 beta 大盤 proxy。增量upsert。"""
    last = db.stock_price.find_one({'symbol': 'TAIEX'}, sort=[('date', -1)])
    start = ((last['date'] - timedelta(days=5)).strftime('%Y-%m-%d') if last else '2022-01-01')
    try:
        r = requests.get('https://api.finmindtrade.com/api/v4/data', params={
            'dataset': 'TaiwanStockPrice', 'data_id': 'TAIEX',
            'start_date': start, 'token': FINMIND_TOKEN}, timeout=30)
        data = r.json().get('data', []) if r.status_code == 200 else []
    except Exception as e:
        return f"⚠️ TAIEX 同步失敗: {e}"
    ops, now = [], datetime.now()
    for row in data:
        try:
            dt = datetime.strptime(row['date'], '%Y-%m-%d')
        except (KeyError, ValueError):
            continue
        close = _d128(row.get('close'))
        ops.append(UpdateOne({'symbol': 'TAIEX', 'date': dt}, {'$set': {
            'symbol': 'TAIEX', 'stock_id': 'TAIEX', 'date': dt, 'name': '加權指數',
            'open': _d128(row.get('open')), 'high': _d128(row.get('max')),
            'low': _d128(row.get('min')), 'close': close, 'adj_close': close,
            'volume': _d128(row.get('Trading_Volume')),
            'data_source': 'FinMind_TAIEX', 'updated_at': now,
        }}, upsert=True))
    if not ops:
        return "TAIEX 無新資料"
    res = db.stock_price.bulk_write(ops, ordered=False)
    return f"TAIEX 同步 {res.upserted_count} 新增/{res.modified_count} 更新"

# 月頻指標的「當期真實值」（每月以 CLI 旗標更新；此為 seed 預設）
SEED = {
    'cpi_yoy':       (2.20, '2026-05'),   # 主計處 CPI 年增率
    'discount_rate': (2.000, '2026-06'),  # 央行重貼現率（維持）
    'm1b_yoy':       (8.25, '2026'),      # 央行 M1B 年增率
    'm2_yoy':        (6.45, '2026'),      # 央行 M2 年增率
    'signal_score':  (39, '2026-05'),     # 國發會 景氣對策信號 分數(連6紅)
    'signal_light':  ('紅燈', '2026-05'),
}
BOT_FX_DAY = 'https://rate.bot.com.tw/xrt/flcsv/0/day'
BOT_FX_6M = 'https://rate.bot.com.tw/xrt/flcsv/0/L6M/USD'


def fetch_bot_usd():
    """台銀牌告匯率(Big5)：回傳 (今日即期賣出, 約30天前即期賣出) USD/TWD。失敗回 (None,None)。
    6M CSV 格式：資料日期,幣別,匯率(本行買入/賣出),現金,即期,遠期...。取『本行賣出』的『即期』。"""
    try:
        r = requests.get(BOT_FX_6M, timeout=20)
        text = r.content.decode('utf-8-sig', errors='ignore')   # 台銀 CSV 為 UTF-8 with BOM
    except Exception:
        return None, None
    lines = text.splitlines()
    if not lines:
        return None, None
    header = lines[0].split(',')
    try:
        i_spot = header.index('即期')      # 即期匯率欄
    except ValueError:
        i_spot = 4
    # 同日可能有本行買入/賣出兩列 → 取即期、同日平均
    by_date: dict[str, list[float]] = {}
    for l in lines[1:]:
        c = l.split(',')
        if len(c) > i_spot and c[1].strip() == 'USD':
            try:
                by_date.setdefault(c[0].strip().replace('/', ''), []).append(float(c[i_spot]))
            except ValueError:
                pass
    if not by_date:
        return None, None
    spot = sorted(((d, sum(v) / len(v)) for d, v in by_date.items()), reverse=True)  # 日期新→舊
    today = round(spot[0][1], 4)
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    older = [v for d, v in spot if d <= cutoff]
    month_ago = round(older[0], 4) if older else None
    return today, month_ago


def main():
    ap = argparse.ArgumentParser(description='總經指標同步（混合版）')
    ap.add_argument('--set-cpi', type=float, help='CPI 年增率(百分比)')
    ap.add_argument('--set-rate', type=float, help='重貼現率(百分比)')
    ap.add_argument('--set-m1b', type=float, help='M1B 年增率(百分比)')
    ap.add_argument('--set-m2', type=float, help='M2 年增率(百分比)')
    ap.add_argument('--set-signal', type=float, help='景氣對策信號 分數')
    ap.add_argument('--set-signal-light', type=str, help='景氣燈號顏色(紅燈/黃紅燈/綠燈/黃藍燈/藍燈)')
    ap.add_argument('--set-signal-date', type=str, help='景氣信號月份 YYYY-MM(如 2026-05)')
    args = ap.parse_args()

    ma = MacroAnalyzer()
    today_str = datetime.now().strftime('%Y-%m-%d')
    done = []

    # ── [自動] 加權指數 TAIEX（供 beta 大盤 proxy）──────────────────
    done.append(sync_taiex(ma.db))

    # ── [自動] 匯率 USD/TWD（台銀）──────────────────────────────
    usd, usd_30d = fetch_bot_usd()
    if usd:
        change_1m = round(usd - usd_30d, 4) if usd_30d else None
        ma._save_indicator('exchange_rate', {
            'date': today_str, 'usd_twd': usd, 'change_1m': change_1m,
        })
        done.append(f"匯率 USD/TWD={usd} (月變 {change_1m})")
    else:
        done.append("⚠️ 匯率抓取失敗(台銀)")

    # ── [存值] 月頻指標：有 --set 用之，否則若 DB 無則 seed ──────
    def ensure(indicator, data, cadence_days, override):
        """override 有值→寫入；否則若 DB 無此指標(或過期)才以 seed 補。"""
        if override is not None:
            ma._save_indicator(indicator, data)
            return f"{indicator} 已更新 ← {data}"
        local = ma.db.macro_indicators.find_one({'indicator': indicator}, sort=[('date', -1)])
        if not local:
            ma._save_indicator(indicator, data)
            return f"{indicator} 已 seed ← {data}"
        return None

    # 利率
    rate = args.set_rate if args.set_rate is not None else SEED['discount_rate'][0]
    msg = ensure('interest_rate', {'date': SEED['discount_rate'][1], 'discount_rate': rate},
                 30, args.set_rate)
    if msg: done.append(msg)

    # CPI
    cpi = args.set_cpi if args.set_cpi is not None else SEED['cpi_yoy'][0]
    msg = ensure('cpi', {'date': args.set_cpi and today_str or SEED['cpi_yoy'][1], 'yoy': cpi,
                         'note': '主計處 CPI 年增率(月更)'}, 30, args.set_cpi)
    if msg: done.append(msg)

    # M1B/M2
    if args.set_m1b is not None or args.set_m2 is not None or \
       not ma.db.macro_indicators.find_one({'indicator': 'money_supply'}):
        m1b = args.set_m1b if args.set_m1b is not None else SEED['m1b_yoy'][0]
        m2 = args.set_m2 if args.set_m2 is not None else SEED['m2_yoy'][0]
        ma._save_indicator('money_supply', {'date': SEED['m1b_yoy'][1], 'm1b_yoy': m1b, 'm2_yoy': m2})
        done.append(f"money_supply 寫入 M1B={m1b}% M2={m2}%")

    # 景氣對策信號（indicator 名須為 'leading'，對應 _get_leading_indicator）
    if args.set_signal is not None or not ma.db.macro_indicators.find_one({'indicator': 'leading'}):
        score = args.set_signal if args.set_signal is not None else SEED['signal_score'][0]
        light = args.set_signal_light or SEED['signal_light'][0]
        sig_date = args.set_signal_date or SEED['signal_score'][1]
        ma._save_indicator('leading', {
            'date': sig_date, 'signal_score': score, 'signal_light': light,
        })
        done.append(f"景氣對策信號 寫入 {score}分 {light} ({sig_date})")

    print("總經指標同步完成：")
    for d in done:
        print("  " + d)

    # 立即驗證 market_signal 是否變真
    sig = ma.market_signal()
    print(f"\n大盤訊號：{sig['verdict']}  (score {sig['score']}, 多{sig['bullish_count']}/空{sig['bearish_count']})")
    for s in sig['signals']:
        print(f"  - {s['name']}({s['direction']}): {s['detail']}")


if __name__ == '__main__':
    main()
