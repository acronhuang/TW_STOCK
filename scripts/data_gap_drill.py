#!/usr/bin/env python3
"""缺口回補失敗路徑演練（在正式庫執行，但只用 *_drill 暫存集合，結束後刪除，不碰真實登記簿與告警）。

驗證：同一缺口回補連續失敗 → 嘗試次數累積 → 第 3 次轉 failed → 只告警一次 → 之後不再重試。
另外以「所有補抓指令都失敗」跑一次開機補跑流程，確認失敗訊息會寫進通知而不中斷。
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.data_gap_repair import MongoRegister  # noqa: E402
from src.config import get_db  # noqa: E402
from src.data_gap import runner  # noqa: E402
from src.data_gap.models import Gap  # noqa: E402
from src.ops import boot_catchup  # noqa: E402

REGISTER, ALERTS = "data_gap_register_drill", "schedule_alerts_drill"


def failing_repair_drill(db) -> bool:
    db[REGISTER].drop()
    db[ALERTS].drop()
    attempts = []

    def execute(command):
        attempts.append(command)
        raise RuntimeError("drill: upstream blocked")

    def alert(message):
        db[ALERTS].insert_one({"ts": datetime.now(), "source": "data_gap_drill", "message": message, "resolved": False})

    start = datetime.now()
    for day in range(4):
        runner.run(detect=lambda: ([Gap("stock_price", "20260915")], frozenset()), execute=execute,
                   register=MongoRegister(db[REGISTER]), alert=alert, now=start + timedelta(days=day), apply=True, max_attempts=3)
    doc = db[REGISTER].find_one({"_id": "stock_price:20260915:gap"})
    ok = (doc["status"] == "failed" and doc["attempts"] == 3 and len(attempts) == 3 and db[ALERTS].count_documents({}) == 1)
    print(f"[失敗路徑] status={doc['status']} attempts={doc['attempts']} 實際執行={len(attempts)} 告警={db[ALERTS].count_documents({})} → {'PASS' if ok else 'FAIL'}")
    db[REGISTER].drop()
    db[ALERTS].drop()
    return ok


def failing_boot_drill() -> bool:
    messages = []

    def execute(command):
        raise RuntimeError("drill: command failed")

    result = boot_catchup.run(wait_mongo=lambda: True, notify=messages.append, execute=execute,
                              repair=lambda: {"detected": 0, "repaired": 0, "unrecoverable": 0},
                              boot_start=datetime.now(), previous_boot_end=datetime.now() - timedelta(minutes=30))
    ok = result["caught_up"] and len(result["failures"]) == len(boot_catchup.CATCH_UP_COMMANDS) and "失敗" in messages[0]
    print(f"[開機補跑] caught_up={result['caught_up']} failures={len(result['failures'])} 通知含失敗字樣={'失敗' in messages[0]} → {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    db = get_db()
    print(f"資料庫：{db.name}（僅使用 {REGISTER}、{ALERTS}，結束後刪除）")
    results = [failing_repair_drill(db), failing_boot_drill()]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
