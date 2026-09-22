"""備份健康檢查 —— 偵測 mongodump 備份過期/缺失（靜默失敗）。

背景：目前每週備份，且若 backup_mongodb.sh 失敗只寫 log，沒人會發現。
本檢查掃描備份目錄最新的 tar.gz，超過時限即回報，供排程/監控告警，
消除「以為有備份、其實好幾天沒備成功」的風險。
"""
from __future__ import annotations

import glob
import os
from datetime import datetime


def check_backup_freshness(backup_dir: str, max_age_hours: int = 48,
                           pattern: str = "tw_stock_analysis_*.tar.gz",
                           now: float | None = None) -> dict:
    """檢查備份目錄最新備份是否夠新。

    回傳 {ok, latest, latest_mtime, age_hours, max_age_hours, count}
    """
    now = now if now is not None else datetime.now().timestamp()
    if not os.path.isdir(backup_dir):
        return {"ok": False, "latest": None, "latest_mtime": None,
                "age_hours": None, "max_age_hours": max_age_hours, "count": 0,
                "reason": "備份目錄不存在"}

    files = glob.glob(os.path.join(backup_dir, pattern))
    if not files:
        return {"ok": False, "latest": None, "latest_mtime": None,
                "age_hours": None, "max_age_hours": max_age_hours, "count": 0,
                "reason": "無備份檔"}

    latest = max(files, key=os.path.getmtime)
    mtime = os.path.getmtime(latest)
    age_hours = (now - mtime) / 3600.0
    return {
        "ok": age_hours <= max_age_hours,
        "latest": os.path.basename(latest),
        "latest_mtime": datetime.fromtimestamp(mtime),
        "age_hours": round(age_hours, 1),
        "max_age_hours": max_age_hours,
        "count": len(files),
    }
