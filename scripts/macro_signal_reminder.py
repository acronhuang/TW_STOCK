#!/usr/bin/env python3
"""
景氣對策信號 月底更新提醒（方案A）
==================================
背景：景氣對策信號是國發會獨家產品，唯一機器可讀源(NDC/data.gov.tw)被 WAF 擋
      或需付費金鑰 → 無法自動抓(已驗證)，採手動種子值維護。
本腳本每月由 launchd 觸發：算出目前儲存信號落後幾個月，發 LINE 提醒手動更新，
附上國發會查詢連結與一行更新指令。平時阿甘 LINE 也有 ⚠️過期警示雙保險。

更新指令：python scripts/macro_sync.py --set-signal <分數> --set-signal-light <燈號>
燈號對照：藍燈9~16 黃藍燈17~22 綠燈23~31 黃紅燈32~37 紅燈38~45
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from pymongo import MongoClient


def build_message(db) -> str:
    d = db.macro_indicators.find_one({'indicator': 'leading'}, sort=[('date', -1)])
    data = (d or {}).get('data') or {}
    score = data.get('signal_score')
    light = data.get('signal_light', '?')
    sm = str(data.get('date') or '')[:7]               # 信號月份 YYYY-MM
    now = datetime.now()
    gap = None
    if sm:
        gap = (now.year - int(sm[:4])) * 12 + (now.month - int(sm[5:7]))
    head = "📅 景氣對策信號 更新提醒"
    body = [
        f"目前儲存：{light}({score}分) · {sm}" + (f"（落後 {gap} 個月）" if gap is not None else ""),
        "",
        "國發會約每月27日公布上月信號，請查最新值後更新：",
        "🔗 https://index.ndc.gov.tw/n/zh_tw",
        "",
        "更新指令（在專案目錄執行）：",
        "python scripts/macro_sync.py \\",
        "  --set-signal <分數> --set-signal-light <燈號> --set-signal-date <YYYY-MM>",
        "",
        "燈號：藍9-16 黃藍17-22 綠23-31 黃紅32-37 紅38-45",
    ]
    return head + "\n" + "\n".join(body)


def main():
    no_line = '--no-line' in sys.argv
    db = MongoClient('localhost', 27017)['tw_stock_analysis']
    msg = build_message(db)
    if no_line:
        print(msg)
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
        from src.alerts.line_notifier import LineNotifier
        LineNotifier().send(msg)
        print("✅ 景氣信號更新提醒 LINE 已發送")
    except Exception as e:
        print(f"⚠️ LINE 失敗: {e}")


if __name__ == '__main__':
    main()
