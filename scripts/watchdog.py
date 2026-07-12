#!/usr/bin/env python3
"""
看門狗 / dead-man's-switch（C · 存活錨）。

整套 P0–P3 完整度防護都假設排程 job「會跑」。但若 job 靜默停了——cron 壞掉、
腳本 crash、時區漂移讓它在錯的時間跑——**沒有任何機制會發現「檢查本身沒執行」**。
這是一個完整度系統最諷刺的盲點：自己卻沒有「確認自己活著」的保險。

本腳本獨立於被監控的 job 運行（不同排程、不同進程），比對每個 job 的心跳
（system_heartbeat 集合，由各 job 完成時寫入）落點是否在「應執行的排程窗」內。
落後 → LINE 告警（自帶去重，不會每次都吵）。

用法:
  watchdog.py            檢查所有被監控 job 的心跳，逾期則告警
  watchdog.py --status   只印出各心跳現況，不告警

殘留限制（誠實）：watchdog 自己也靠 cron 跑。若 cron 整個死了，watchdog 也不會跑。
真・外部看門狗需離機 pinger（healthchecks.io 之類）——見 twse_openapi_sync.py 的
HEALTHCHECK_URL 選項：完整度 job 成功時 ping 外部，外部服務在「該 ping 沒來」時告警。
"""
import argparse
import shutil
import sys
from datetime import datetime, timedelta

from pymongo import MongoClient

# 被監控的 job：排程窗定義（給 last_expected 判「上次應執行時刻」）。
#   hour          該 job 每日排定的小時
#   weekdays_only 只在週一~五排（週末不算漏）
#   grace_h       允許 job 執行到 hour+grace_h 才算數（跑很久的 job 緩衝）
#   overdue_h     心跳比「上次應執行時刻」還舊超過這麼多小時 → 判逾期
WATCHED = {
    "integrity": {"name": "完整度檢查/自癒", "hour": 21, "weekdays_only": True,
                  "grace_h": 2, "overdue_h": 1},
    "health":    {"name": "資料健康快照",   "hour": 22, "weekdays_only": True,
                  "grace_h": 2, "overdue_h": 1},
}
REALERT_HOURS = 12  # 同一 job 兩次告警至少間隔（去重，避免每輪都吵）
DISK_WARN_PCT = 85  # 根檔案系統使用率超過此值即告警（曾因 runaway log 逼近磁碟滿）
DISK_PATH = "/"


def last_expected(now, hour, weekdays_only, grace_h):
    """從 now 往回找『最近一個已過 (hour+grace_h) 的排定日』的 hour:00。
    週末/非排程日跳過。找不到（理論上不會）回 None。"""
    probe = now
    for _ in range(14):
        if (not weekdays_only) or probe.weekday() < 5:
            sched = probe.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now >= sched + timedelta(hours=grace_h):
                return sched
        probe = (probe - timedelta(days=1)).replace(
            hour=23, minute=59, second=0, microsecond=0)
    return None


def _line(msg):
    try:
        import os
        sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
        from dotenv import load_dotenv
        load_dotenv("/home/mdsadmin/Stock/tw-stock-analysis/.env")
        from src.alerts.line_notifier import LineNotifier
        n = LineNotifier()
        if n.enabled:
            n.send(f"🐕 {datetime.now():%Y-%m-%d %H:%M} 看門狗\n{msg}")
    except Exception as e:
        print("LINE 發送失敗:", e)


def main():
    ap = argparse.ArgumentParser(description="排程心跳看門狗")
    ap.add_argument("--status", action="store_true", help="只印心跳現況，不告警")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
    now = datetime.now()
    hb = {d["_id"]: d for d in db.system_heartbeat.find()}

    overdue = []
    for job, cfg in WATCHED.items():
        exp = last_expected(now, cfg["hour"], cfg["weekdays_only"], cfg["grace_h"])
        doc = hb.get(job)
        last_run = doc.get("last_run") if doc else None
        # 判逾期：從沒跑過，或上次執行早於「上次應執行時刻 - overdue 容忍」
        threshold = (exp - timedelta(hours=cfg["overdue_h"])) if exp else None
        is_overdue = (last_run is None) or (threshold and last_run < threshold)

        age = f"{(now - last_run).total_seconds()/3600:.1f}h 前" if last_run else "從未執行"
        mark = "🚨 逾期" if is_overdue else "✅"
        print(f"{mark} {job:10}（{cfg['name']}）上次 {last_run} （{age}）"
              f" 應執行於 {exp}")

        if is_overdue and not args.status:
            alerted_at = doc.get("watchdog_alerted_at") if doc else None
            if alerted_at and (now - alerted_at) < timedelta(hours=REALERT_HOURS):
                print(f"    （{REALERT_HOURS}h 內已告警過，跳過去重）")
                continue
            last_str = f"{last_run:%m-%d %H:%M}" if last_run else "從未"
            exp_str = f"{exp:%m-%d %H:%M}" if exp else "?"
            overdue.append(
                f"⚠️ {cfg['name']}（{job}）未如期執行\n"
                f"  應於 {exp_str} 前完成，實際上次執行 {last_str}")
            db.system_heartbeat.update_one(
                {"_id": job}, {"$set": {"watchdog_alerted_at": now}}, upsert=True)

    # 磁碟空間守衛：曾因 runaway log 每小時 1.1GB 逼近磁碟滿而無人知曉
    total, used, free = shutil.disk_usage(DISK_PATH)
    pct = used / total * 100
    gb = free / 1024 ** 3
    disk_alert = None
    print(f"{'🚨' if pct >= DISK_WARN_PCT else '✅'} 磁碟 {DISK_PATH} 使用 {pct:.0f}%"
          f"（剩 {gb:.0f}G）")
    if pct >= DISK_WARN_PCT and not args.status:
        ddoc = hb.get("_disk")
        d_alerted = ddoc.get("watchdog_alerted_at") if ddoc else None
        if not (d_alerted and (now - d_alerted) < timedelta(hours=REALERT_HOURS)):
            disk_alert = (f"💾 磁碟空間吃緊：{DISK_PATH} 已用 {pct:.0f}%（剩 {gb:.0f}G）\n"
                          f"  → 查最大目錄：du -xh / | sort -rh | head；常見元兇為 logs/")
            db.system_heartbeat.update_one(
                {"_id": "_disk"}, {"$set": {"watchdog_alerted_at": now}}, upsert=True)

    problems = list(overdue)
    if disk_alert:
        problems.append(disk_alert)
    if problems and not args.status:
        _line("系統守衛偵測到異常：\n\n" + "\n\n".join(problems)
              + "\n\n→ 排程：systemctl is-active cron；timedatectl　→ 空間：df -h /")
        sys.exit(1)
    elif not args.status:
        print("\n✅ 排程都在窗內、磁碟空間充足")


if __name__ == "__main__":
    main()
