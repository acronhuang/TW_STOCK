#!/usr/bin/env python3
"""每小時更新的失敗告警閘門：連續失敗才告警，狀態存 JSON。

用法：hourly_alert_gate.py STATE_FILE [失敗類別 ...]
輸出：第一行 ALERT 或 SKIP；ALERT 時第二行為持續失敗的類別（空白分隔）、第三行為其中最長的連續失敗次數。
不帶失敗類別代表本輪全部成功。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ops import alert_throttle  # noqa: E402


def main(argv: list[str]) -> int:
    state_path, failed = Path(argv[1]), argv[2:]
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
    send, state, persistent = alert_throttle.decide(state, failed, datetime.now())
    state_path.write_text(json.dumps(state, default=alert_throttle.encode, ensure_ascii=False))
    if send:
        print("ALERT")
        print(" ".join(persistent))
        print(max(state["counts"][name] for name in persistent))
    else:
        print("SKIP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
