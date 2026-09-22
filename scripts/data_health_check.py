#!/usr/bin/env python3
"""資料健康檢查排程入口 —— 新鮮度 + 覆蓋率 + 備份健康。

用法（建議 cron 每時或每日）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/data_health_check.py

輸出：寫入 data_health_history（歷史）+ schedule_alerts（有問題才寫，網頁可見），
並印出摘要。全程唯讀主資料，不改動任何業務集合。
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_DATA_HEALTH_HISTORY, COLL_SCHEDULE_ALERTS  # noqa: E402
from src.monitoring.backup_health import check_backup_freshness  # noqa: E402
from src.monitoring.data_quality import run_health_check  # noqa: E402

# 關鍵集合的新鮮度/覆蓋率門檻（依實機 schema 校正；可移至設定）。
# 資料新鮮度以 updated_at（寫入時間）為準，反映「是否持續更新」。
HEALTH_CONFIG = {
    "freshness": {
        "stock_price": {"date_field": "date", "max_age_days": 4},
        "stock_factors": {"date_field": "date", "max_age_days": 4},
        "institutional_flow": {"date_field": "date", "max_age_days": 4},
        "quarterly_earnings": {"date_field": "updated_at", "max_age_days": 120},
        "monthly_revenue": {"date_field": "updated_at", "max_age_days": 40},
        "macro_indicators": {"date_field": "updated_at", "max_age_days": 40},
    },
    "coverage": {
        "taiwan_stock_info": 1000,
    },
}
BACKUP_DIR = os.getenv("MONGO_BACKUP_DIR",
                       str(Path.home() / "Stock" / "mongodb_backups"))


def main() -> int:
    db = get_db()
    now = datetime.now()
    report = run_health_check(db, HEALTH_CONFIG, now=now)

    backup = check_backup_freshness(BACKUP_DIR, max_age_hours=48)
    if not backup["ok"]:
        report["alerts"].append(
            f"[備份] 最新備份過期/缺失：{backup.get('latest')}（{backup.get('age_hours')}h）")
        report["ok"] = False
    report["backup"] = backup

    # 寫歷史
    try:
        db[COLL_DATA_HEALTH_HISTORY].insert_one({
            "ts": now, "ok": report["ok"], "stale_count": report["stale_count"],
            "low_coverage_count": report["low_coverage_count"],
            "alerts": report["alerts"], "backup_ok": backup["ok"],
        })
    except Exception as e:
        print(f"⚠️ 寫入 {COLL_DATA_HEALTH_HISTORY} 失敗：{e}")

    # 有問題才寫告警（網頁可見）
    if report["alerts"]:
        try:
            db[COLL_SCHEDULE_ALERTS].insert_one({
                "ts": now, "level": "warning", "source": "data_health_check",
                "message": f"資料健康異常 {len(report['alerts'])} 項",
                "detail": {"alerts": report["alerts"]}, "resolved": False,
            })
        except Exception as e:
            print(f"⚠️ 寫入 {COLL_SCHEDULE_ALERTS} 失敗：{e}")

    # 摘要
    status = "✅ 全部正常" if report["ok"] else f"🔴 {len(report['alerts'])} 項異常"
    print(f"[{now:%Y-%m-%d %H:%M}] 資料健康檢查：{status}")
    for a in report["alerts"]:
        print(f"  - {a}")
    print(f"備份：{'✅' if backup['ok'] else '🔴'} 最新 {backup.get('latest')} "
          f"（{backup.get('age_hours')}h，共 {backup.get('count')} 份）")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
