#!/usr/bin/env python3
"""團隊分析角色失敗率巡檢 —— 執行中就能發現劣化，不必等整輪跑完。

用法:
  role_failure_watch.py                 看最近一輪，印報告
  role_failure_watch.py --alert         超標才寫 schedule_alerts（網頁看，不發 LINE）
  role_failure_watch.py --window 200    只看日誌最後 N 個標的（預設 200）

為什麼需要這支
--------------
team_daily_verified.py 內建的失敗率統計只在 main() 收尾時輸出。全市場一輪要跑
3 天以上，若第 2 小時就開始劣化，那個統計要 3 天後才會出現 —— 等於沒有告警。

角色呼叫失敗時 reports[role] 會被寫成「分析失敗: …」字串，而顧問整合與合議
照樣拿它去整合、投票。流程全綠、log 正常，只是那份意見其實是錯誤訊息。
這是靜默降級，必須在執行中就看得見。

判準依實測（2026-08-15）:
  角色並行前 0.1%(50,965 次呼叫) ｜ 8/14 那輪 0.9% ｜ 6 併發時最高 18.8%
故門檻設 3%：超過就不是零星網路抖動，而是系統性打爆 GPU，該調降 TEAM_ROLE_PARALLEL。
"""
import os
import re
import sys
import time
import argparse
import datetime

LOG = "/home/mdsadmin/Stock/tw-stock-analysis/logs/cron_weekly_team_full.log"
# 例:      📈技術 (qwen3-14b:latest) 158.1s   /   ... ?s   /   ... 12.3s retry×2
ROLE = re.compile(r"^\s*\S+?\s*\(([^)]+)\)\s+(\S+?)s(\s+retry×(\d+))?\s*$")
STOCK = re.compile(r"^🏛️\s")


def scan(path, window):
    """回 (標的數, 角色呼叫數, 失敗數, 重試成功數)。只看最後 window 個標的。"""
    lines = []
    with open(path, errors="ignore") as f:
        lines = f.readlines()
    # 從尾巴往回找第 window 個標的起點
    starts = [i for i, l in enumerate(lines) if STOCK.match(l)]
    if not starts:
        return 0, 0, 0, 0
    begin = starts[-window] if len(starts) > window else starts[0]
    seg = lines[begin:]
    n_stock = sum(1 for l in seg if STOCK.match(l))
    tot = bad = retried = 0
    for l in seg:
        m = ROLE.match(l.rstrip())
        if not m:
            continue
        tot += 1
        if m.group(2) == "?":
            bad += 1
        if m.group(4):
            retried += 1
    return n_stock, tot, bad, retried


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=LOG)
    ap.add_argument("--window", type=int, default=200, help="只看最後 N 個標的")
    ap.add_argument("--max", type=float, default=0.03, help="失敗率門檻")
    ap.add_argument("--max-age-min", type=float, default=90.0,
                    help="日誌超過這麼久沒更新即視為無資料（預設 90 分）")
    ap.add_argument("--alert", action="store_true")
    a = ap.parse_args()

    # ADR-0002 條件 2：無資料 ≠ 通過。
    # 本檢查讀日誌尾端算失敗率,若團隊分析已結束、日誌停止增長,
    # 舊數字會被永遠重複回報並顯示通過 —— 結構上不會失敗的檢查比沒有檢查更糟。
    # 三態:0=通過 / 1=未通過 / 2=無資料。無資料不是失敗,但也絕不是通過。
    try:
        age_min = (time.time() - os.path.getmtime(a.log)) / 60.0
    except OSError as e:
        print(f"⚪ 無資料：讀不到日誌 {a.log}（{e}）")
        return 2
    if age_min > a.max_age_min:
        print(f"⚪ 無資料：日誌已 {age_min:.0f} 分鐘未更新"
              f"（上限 {a.max_age_min:.0f} 分），團隊分析可能未在執行。")
        print("   這不是通過，也不是失敗 —— 是這條需求此刻無從判定。")
        return 2

    n_stock, tot, bad, retried = scan(a.log, a.window)
    if not tot:
        print("⚪ 無資料：日誌中尚無角色呼叫紀錄")
        return 2
    print(f"（日誌 {age_min:.0f} 分鐘前更新過，資料為當前）")

    rate = bad / tot
    print(f"=== 角色失敗率巡檢（最後 {n_stock} 個標的）===")
    print(f"  角色呼叫 {tot} 次 / 失敗 {bad} 次 = {rate*100:.1f}%")
    print(f"  重試後才成功 {retried} 次 "
          f"({retried*100.0/tot:.1f}%) —— 這些若無重試就會變成失敗")
    print(f"  門檻 {a.max*100:.0f}%")

    if rate <= a.max:
        print("  ✅ 未超標")
        return 0

    print(f"  🔴 超標 —— 失敗的報告內容是錯誤訊息，卻仍被顧問整合與合議採用，"
          f"分析品質已靜默降級")
    print(f"     建議：調降 TEAM_ROLE_PARALLEL（目前預設 3）或提高 ROLE_RETRY")
    if a.alert:
        try:
            from pymongo import MongoClient
            db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
            db.schedule_alerts.create_index([("ts", -1)])
            db.schedule_alerts.insert_one({
                "ts": datetime.datetime.now(), "level": "warning",
                "source": "team_role_failure_watch",
                "message": (f"🔴 團隊分析角色失敗率 {rate*100:.1f}%（最後 {n_stock} 檔、"
                            f"{bad}/{tot} 次呼叫），超過 {a.max*100:.0f}% 門檻。"
                            f"失敗的報告內容是錯誤訊息仍被顧問整合採用 —— "
                            f"建議調降 TEAM_ROLE_PARALLEL"),
                "detail": {"stocks": n_stock, "calls": tot, "failed": bad,
                           "retried_ok": retried, "rate": round(rate, 4)},
                "resolved": False})
            print("  [alert] 已寫 schedule_alerts")
        except Exception as e:
            print(f"  ⚠️ 寫告警失敗: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
