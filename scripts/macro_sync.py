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
import io
import csv
import re
import zipfile
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
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
    """USD/TWD 即期賣出:回傳 (今日即期賣出, 約30天前即期賣出)。失敗回 (None,None)。
    2026-06-29 起台銀免費 CSV(rate.bot.com.tw/xrt/flcsv)被 bot 挑戰(Challenge Validation)擋,
    server 端 requests 過不了 → 改用 FinMind TaiwanExchangeRate(同『本行賣出的即期』=spot_sell 語意)。"""
    token = os.getenv('FINMIND_API_TOKEN')
    start_date = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
    try:
        r = requests.get('https://api.finmindtrade.com/api/v4/data', params={
            'dataset': 'TaiwanExchangeRate', 'data_id': 'USD',
            'start_date': start_date, 'token': token}, timeout=20)
        rows = r.json().get('data', [])
    except Exception:
        return None, None
    series = [(d['date'], d.get('spot_sell')) for d in rows if d.get('spot_sell')]
    if not series:
        return None, None
    series.sort(reverse=True)  # 日期新→舊
    today = round(float(series[0][1]), 4)
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    older = [v for d, v in series if d <= cutoff]
    month_ago = round(float(older[0]), 4) if older else None
    return today, month_ago


# ── 政府免費開放源自動抓取(2026-08-10 取代 SEED 硬編碼;抓失敗保留舊值不 null) ──
_UA = {'User-Agent': 'Mozilla/5.0'}
CPI_XML_URL = 'https://ws.dgbas.gov.tw/001/Upload/461/relfile/11525/230555/pr0101a1m.xml'
NDC_SIGNAL_ZIP = ('https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkyL2VhMjM1YmQ5LWQwNTItNGE2OS1hYmZjLWQ1Yzc4NWQzZDBlMi56aXA%3d&n=5pmv5rCj5oyH5qiZ5Y%2bK54eI6JmfLnppcA%3d%3d&icon=.zip')
CBC_MONEY_CSV = 'https://www.cbc.gov.tw/public/data/OpenData/經研處/EF15M01.csv'


def _to_ym(pp):
    """'2026M07' 或 '202606' → '2026-07'。"""
    pp = (pp or '').strip()
    m = re.match(r'(\d{4})M(\d{2})', pp) or re.match(r'(\d{4})(\d{2})$', pp)
    return '{}-{}'.format(m.group(1), m.group(2)) if m else pp


def fetch_cpi_yoy():
    """主計總處基本分類指數 XML → (總指數年增率 float, 'YYYY-MM')。失敗回 None。
    verify=False:ws.dgbas.gov.tw 憑證鏈不全(只讀公開資料)。TYPE 直接有『年增率(%)』免自算。"""
    try:
        r = requests.get(CPI_XML_URL, headers=_UA, timeout=45, verify=False)
        txt = r.content.decode('utf-8')
        obs = re.findall(
            r'<Obs><Item>(總指數[^<]*)</Item><TIME_PERIOD>([^<]+)</TIME_PERIOD>'
            r'<FREQ>[^<]*</FREQ><TYPE>(年增率[^<]*)</TYPE>\s*<Item_VALUE>([^<]*)</Item_VALUE>', txt)
        rows = sorted((_to_ym(pp), v) for (_i, pp, _t, v) in obs if v.strip())
        if not rows:
            return None
        ym, v = rows[-1]
        return round(float(v), 2), ym
    except Exception:
        return None


def fetch_business_signal():
    """國發會 景氣指標及燈號 ZIP → (綜合分數 float, 燈號 str, 'YYYY-MM')。失敗回 None。"""
    try:
        r = requests.get(NDC_SIGNAL_ZIP, headers=_UA, timeout=45)
        if r.content[:2] != b'PK':
            return None
        body = zipfile.ZipFile(io.BytesIO(r.content)).read('景氣指標與燈號.csv').decode('utf-8-sig')
        rows = [row for row in csv.reader(io.StringIO(body))
                if row and re.match(r'\d{6}', row[0].strip())]
        if not rows:
            return None
        last = rows[-1]
        light = last[-1].strip()
        if light and not light.endswith('燈'):
            light += '燈'
        return float(last[-2]), light, _to_ym(last[0])
    except Exception:
        return None


def fetch_money_supply():
    """央行 貨幣總計數日平均數(月) CSV → (M1B年增率, M2年增率, 'YYYY-MM')。失敗回 None。
    末四欄= M1B原始值,M1B年增率,M2原始值,M2年增率。"""
    try:
        r = requests.get(CBC_MONEY_CSV, headers=_UA, timeout=45)
        body = r.content.decode('utf-8-sig')
        rows = [row for row in csv.reader(io.StringIO(body))
                if row and re.match(r'\d{4}M\d{2}', row[0])]
        if not rows:
            return None
        last = rows[-1]
        return round(float(last[-3]), 2), round(float(last[-1]), 2), _to_ym(last[0])
    except Exception:
        return None


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
        done.append("⚠️ 匯率抓取失敗(FinMind)")

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

    # CPI ← 主計總處自動抓;失敗保留舊值(不 null)
    if args.set_cpi is not None:
        ma._save_indicator('cpi', {'date': today_str, 'yoy': args.set_cpi,
                                   'note': '主計處 CPI 年增率(手動)'})
        done.append(f"cpi 手動更新 ← {args.set_cpi}%")
    else:
        got = fetch_cpi_yoy()
        if got:
            yoy, ym = got
            ma._save_indicator('cpi', {'date': ym, 'yoy': yoy, 'note': '主計處 CPI 年增率(自動)'})
            done.append(f"cpi 自動 ← {yoy}% @{ym}")
        elif not ma.db.macro_indicators.find_one({'indicator': 'cpi'}):
            ma._save_indicator('cpi', {'date': SEED['cpi_yoy'][1], 'yoy': SEED['cpi_yoy'][0],
                                       'note': 'seed'})
            done.append("⚠️ cpi 抓取失敗,以 seed 補")
        else:
            done.append("⚠️ cpi 抓取失敗,保留舊值")

    # M1B/M2 ← 央行自動抓;失敗保留舊值
    if args.set_m1b is not None or args.set_m2 is not None:
        m1b = args.set_m1b if args.set_m1b is not None else SEED['m1b_yoy'][0]
        m2 = args.set_m2 if args.set_m2 is not None else SEED['m2_yoy'][0]
        ma._save_indicator('money_supply', {'date': today_str, 'm1b_yoy': m1b, 'm2_yoy': m2})
        done.append(f"money_supply 手動 ← M1B={m1b}% M2={m2}%")
    else:
        got = fetch_money_supply()
        if got:
            m1b, m2, ym = got
            ma._save_indicator('money_supply', {'date': ym, 'm1b_yoy': m1b, 'm2_yoy': m2})
            done.append(f"money_supply 自動 ← M1B={m1b}% M2={m2}% @{ym}")
        elif not ma.db.macro_indicators.find_one({'indicator': 'money_supply'}):
            ma._save_indicator('money_supply', {'date': SEED['m1b_yoy'][1],
                                                'm1b_yoy': SEED['m1b_yoy'][0], 'm2_yoy': SEED['m2_yoy'][0]})
            done.append("⚠️ money_supply 抓取失敗,以 seed 補")
        else:
            done.append("⚠️ money_supply 抓取失敗,保留舊值")

    # 景氣對策信號 ← 國發會自動抓;失敗保留舊值(indicator 名須為 'leading')
    if args.set_signal is not None:
        ma._save_indicator('leading', {
            'date': args.set_signal_date or today_str, 'signal_score': args.set_signal,
            'signal_light': args.set_signal_light or SEED['signal_light'][0]})
        done.append(f"景氣 手動 ← {args.set_signal}分")
    else:
        got = fetch_business_signal()
        if got:
            score, light, ym = got
            ma._save_indicator('leading', {'date': ym, 'signal_score': score, 'signal_light': light})
            done.append(f"景氣 自動 ← {score}分 {light} @{ym}")
        elif not ma.db.macro_indicators.find_one({'indicator': 'leading'}):
            ma._save_indicator('leading', {'date': SEED['signal_score'][1],
                                           'signal_score': SEED['signal_score'][0],
                                           'signal_light': SEED['signal_light'][0]})
            done.append("⚠️ 景氣 抓取失敗,以 seed 補")
        else:
            done.append("⚠️ 景氣 抓取失敗,保留舊值")

    print("總經指標同步完成：")
    for d in done:
        print("  " + d)

    # 過期防呆:月頻指標 >=3 個月未更新→寫 schedule_alerts(進網頁「排程警報」)。
    # 為何在此而非 data_freshness_audit:後者是 collection 層級,macro_indicators 混多指標,
    # 最新的日頻 exchange_rate 會讓整表恆顯 ✅,遮蔽 per-indicator 的 cpi/景氣過期。
    # 門檻 3 個月:月頻資料本有 1-2 月出版落後,>=3 才確定是政府源抓取持續失效(非正常 cadence)。
    def _months_behind(ym):
        m = re.match(r'(\d{4})-(\d{2})', str(ym or '')) or re.match(r'(\d{4})M(\d{2})', str(ym or ''))
        if not m:
            return 99
        now = datetime.now()
        return (now.year - int(m.group(1))) * 12 + (now.month - int(m.group(2)))

    stale = []
    for ind, label in [('cpi', 'CPI'), ('leading', '景氣信號'), ('money_supply', 'M1B/M2')]:
        doc = ma.db.macro_indicators.find_one({'indicator': ind}, sort=[('date', -1)])
        mb = _months_behind((doc or {}).get('date', ''))
        if mb >= 3:
            stale.append(f"{label}({ind}) 最新 {(doc or {}).get('date')} 落後 {mb} 個月")
    if stale:
        msg = "⚠️ 總經指標過期(政府免費源抓取疑失效):" + chr(10) + chr(10).join("- " + x for x in stale)
        try:
            ma.db.schedule_alerts.create_index([('ts', -1)])
            ma.db.schedule_alerts.insert_one({
                'ts': datetime.now(), 'level': 'error', 'source': 'macro_sync',
                'message': msg, 'resolved': False})
            print(f"[alert] 已寫入 schedule_alerts({len(stale)} 個過期指標)")
        except Exception as e:
            print(f"[alert] schedule_alerts 寫入失敗:{e!r}")

    # 立即驗證 market_signal 是否變真
    sig = ma.market_signal()
    print(f"\n大盤訊號：{sig['verdict']}  (score {sig['score']}, 多{sig['bullish_count']}/空{sig['bearish_count']})")
    for s in sig['signals']:
        print(f"  - {s['name']}({s['direction']}): {s['detail']}")


if __name__ == '__main__':
    main()
