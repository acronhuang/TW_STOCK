#!/usr/bin/env python3
"""檢查 FinMind 額度：最近的每小時下載日誌有沒有 HTTP 402。

用法：python scripts/check_finmind_quota.py [--runs 72] [--alert]
有 402、輪次不足、沒有日誌或日誌停止產生時以非零狀態結束；--alert 另寫 schedule_alerts（source=finmind_quota，7 天內相同未處理告警不重複）。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ops import finmind_quota  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=72, help="看最近幾輪每小時下載")
    parser.add_argument("--log-dir", default=str(finmind_quota.LOG_DIR))
    parser.add_argument("--alert", action="store_true")
    args = parser.parse_args(argv)

    ok, message, _ = finmind_quota.check(args.log_dir, datetime.now(), runs=args.runs)
    print(("OK   " if ok else "FAIL ") + message)
    if ok:
        return 0
    if args.alert:
        from src.config import get_db
        from src.ops.alert_dedup import insert_once
        written = insert_once(get_db()["schedule_alerts"], {
            "ts": datetime.now(), "level": "warning", "source": "finmind_quota",
            "message": message, "resolved": False})
        print("[alert] 已寫入 schedule_alerts" if written else "[alert] 已有相同的未處理告警，略過")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
