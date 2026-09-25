#!/usr/bin/env python3
"""systemd timer/service 失敗即時告警 —— 供各單元 `OnFailure=tw-alert@%n.service` 呼叫。

遷 systemd 後,oneshot 失敗只進 journal、不會主動通知(需等資料新鮮度落後才被間接抓到)。
本腳本在單元失敗當下寫一筆 schedule_alerts（source=systemd_timer_fail,24h 去重,
附 journal 尾巴),讓網頁🔔即時可見,補齊觀測性缺口。

用法:systemd_alert.py <failed-unit-name>
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from pymongo import MongoClient


def main() -> int:
    unit = sys.argv[1] if len(sys.argv) > 1 else "unknown.service"
    try:
        tail = subprocess.run(
            ["journalctl", "--user", "-u", unit, "-n", "12", "--no-pager"],
            capture_output=True, text=True, timeout=10,
        ).stdout[-1800:]
    except Exception:
        tail = ""
    try:
        db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                         serverSelectionTimeoutMS=5000).tw_stock_analysis
        since = datetime.now() - timedelta(hours=24)
        dup = db.schedule_alerts.find_one({
            "source": "systemd_timer_fail", "resolved": False,
            "detail.unit": unit, "ts": {"$gte": since}})
        if dup:
            print(f"[systemd_alert] 24h 內已有 {unit} 告警,略過")
            return 0
        db.schedule_alerts.create_index([("ts", -1)])
        db.schedule_alerts.insert_one({
            "ts": datetime.now(), "level": "warning", "source": "systemd_timer_fail",
            "message": f"⚠️ 排程任務失敗:{unit}（systemd timer）",
            "detail": {"unit": unit, "journal_tail": tail},
            "resolved": False,
        })
        print(f"[systemd_alert] 已寫 schedule_alerts（unit={unit}）")
        return 0
    except Exception as e:
        print(f"[systemd_alert] 寫入失敗:{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
