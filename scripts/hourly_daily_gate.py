#!/usr/bin/env python3
"""每小時下載的每日一次閘門。

用法：
  hourly_daily_gate.py check 類別 狀態檔   該跑回 0；今天已完成或還沒到時間回 10
  hourly_daily_gate.py done  類別 狀態檔   記下今天已完成（非每日類別不記）
閘門本身出錯一律回 0（照舊每小時跑），不因閘門壞掉而停掉下載。
"""
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ops import daily_gate  # noqa: E402

NOT_DUE = 10


def main(argv, now=datetime.now):
    try:
        action, category, state_path = argv[1], argv[2], argv[3]
        categories, hour = daily_gate.settings()
        if action == "check":
            due = daily_gate.is_due(category, now(), daily_gate.load(state_path), categories, hour)
            return 0 if due else NOT_DUE
        if action == "done":
            daily_gate.mark_done(state_path, category, now(), categories)
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"daily gate error: {exc}", file=sys.stderr)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
