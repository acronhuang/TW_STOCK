#!/usr/bin/env python3
"""
盤後資料落地檢查（validator 觀察期用）

起因 2026-07-19：validator 觀察期需人工確認當日 stock_price 是否落地，
靠人記會漏，故排 cron。同時檢查 institutional_flow 的 T+1 回補
（T86 隔一交易日才補齊，見記憶 institutional-flow-t1-false-alarm）。

設計原則：無論通過與否都發一則 LINE。
「沒收到訊息 = 正常」會讓腳本自身故障看起來像健康，
而 LINE 靜默不發正是本專案踩過兩次的坑（見記憶 line-notifier-needs-dotenv）。
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pymongo import MongoClient

PROJECT = Path('/home/mdsadmin/Stock/tw-stock-analysis')

# 主板筆數基線，來自記憶 data-audit-baseline-2026-07-18（06-22~07-17 觀測區間）
MAIN_BOARD_MIN = 1900
MAIN_BOARD_MAX = 2050
# institutional_flow 單日回補後的合理下限（正常約 2,000~2,060）
INST_BACKFILL_MIN = 1800

TPE = timezone(timedelta(hours=8))


def utc_midnight(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def prev_trading_day(db, d):
    """往前找最近一個 stock_price 有資料的日期（避開假日/天災停市）。"""
    doc = db.stock_price.find_one(
        {'date': {'$lt': utc_midnight(d)}}, sort=[('date', -1)], projection={'date': 1})
    return doc['date'] if doc else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=None, help='檢查日期 YYYY-MM-DD，預設今天(台北)')
    ap.add_argument('--no-line', action='store_true', help='只印報告不發 LINE')
    args = ap.parse_args()

    today = (datetime.strptime(args.date, '%Y-%m-%d').date() if args.date
             else datetime.now(TPE).date())

    db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
    dt = utc_midnight(today)

    lines = [f'📋 盤後資料檢查 {today}']
    ok = True

    # ── 1. 當日 stock_price 主板筆數 ──────────────────────────────
    main_n = db.stock_price.count_documents(
        {'date': dt, 'stock_id': {'$regex': r'^[0-9]{4}$'}})
    total_n = db.stock_price.count_documents({'date': dt})

    if main_n == 0:
        ok = False
        lines.append(f'❌ stock_price 當日 0 筆（漏抓或休市？需人工確認）')
    elif MAIN_BOARD_MIN <= main_n <= MAIN_BOARD_MAX:
        lines.append(f'✅ stock_price 主板 {main_n} 筆（總 {total_n}）')
    else:
        ok = False
        lines.append(f'⚠️ stock_price 主板 {main_n} 筆，超出 '
                     f'{MAIN_BOARD_MIN}~{MAIN_BOARD_MAX} 區間（總 {total_n}）')

    # ── 2. 前一交易日 institutional_flow 是否 T+1 回補 ─────────────
    prev = prev_trading_day(db, today)
    if prev is None:
        ok = False
        lines.append('❌ 找不到前一交易日，stock_price 可能異常')
    else:
        inst_n = db.institutional_flow.count_documents({'date': prev})
        pd = prev.strftime('%m-%d')
        if inst_n >= INST_BACKFILL_MIN:
            lines.append(f'✅ institutional_flow {pd} 已回補 {inst_n} 筆')
        else:
            ok = False
            lines.append(f'⚠️ institutional_flow {pd} 僅 {inst_n} 筆，'
                         f'T+1 回補可能失敗（應 ≥{INST_BACKFILL_MIN}）')

    lines.append('')
    lines.append('全部通過 ✅' if ok else '有項目需查看 ⚠️')
    report = '\n'.join(lines)
    print(report, flush=True)

    if not args.no_line:
        try:
            # 必須先 load_dotenv，否則 cron 環境下 LineNotifier 靜默不發
            from dotenv import load_dotenv
            load_dotenv(str(PROJECT / '.env'))
            sys.path.insert(0, str(PROJECT))
            from src.alerts.line_notifier import LineNotifier
            notifier = LineNotifier()
            if not notifier.enabled:
                print('LINE notifier 未啟用（enabled=False）', flush=True)
            else:
                notifier.send(report)
                print('LINE 已送出', flush=True)
        except Exception as e:
            print(f'LINE 發送失敗: {e.__class__.__name__}: {e}', flush=True)

    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
