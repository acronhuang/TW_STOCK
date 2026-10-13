#!/usr/bin/env python3
"""檢查異機備份（本機 Windows 拉回的 MongoDB 備份）是否過期。

用法：python scripts/check_offsite_backup.py [--alert]
過期或無紀錄時以非零狀態結束；加 --alert 另寫一筆 schedule_alerts（source=offsite_backup，7 天內相同未處理告警不重複）。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ops import offsite_backup  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert", action="store_true")
    parser.add_argument("--marker", default=str(offsite_backup.MARKER))
    args = parser.parse_args(argv)

    ok, message = offsite_backup.check(Path(args.marker), datetime.now())
    print(("OK  " if ok else "FAIL ") + message)
    if ok:
        return 0
    if args.alert:
        from src.config import get_db
        from src.ops.alert_dedup import insert_once
        written = insert_once(get_db()["schedule_alerts"], {
            "ts": datetime.now(), "level": "warning", "source": "offsite_backup",
            "message": message, "resolved": False})
        print("[alert] 已寫入 schedule_alerts" if written else "[alert] 已有相同的未處理告警，略過")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
