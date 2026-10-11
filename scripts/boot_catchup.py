#!/usr/bin/env python3
"""開機補跑（systemd user service，開機後執行一次）。

cron 不會補跑停機期間錯過的排程，而只給最新日的來源（OpenAPI）錯過就永遠補不回。
主機停機超過 10 分鐘時：補抓最新日資料 → 回補可補的缺口 → LINE 通知停機時間與結果。
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ops import boot_catchup, downtime  # noqa: E402

ALERT_SOURCE = "boot_catchup"
SPOOL = PROJECT_ROOT / "logs" / "line_spool.jsonl"
COMMAND_TIMEOUT_SEC = 1800
MONGO_WAIT_SEC = 600


def boot_start() -> datetime:
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    return datetime.fromtimestamp(time.time() - uptime)


def previous_boot_end() -> datetime | None:
    """上一次開機最後一筆日誌的時間；journal 不可用時回 None（視為停機時間未知）。"""
    try:
        result = subprocess.run(["journalctl", "-b", "-1", "-n", "1", "-o", "short-unix", "--no-pager"],
                                capture_output=True, text=True, timeout=30)
        first = result.stdout.strip().splitlines()[0].split()[0]
        return datetime.fromtimestamp(float(first))
    except Exception:  # noqa: BLE001
        return None


def wait_mongo() -> bool:
    from pymongo import MongoClient
    deadline = time.time() + MONGO_WAIT_SEC
    while time.time() < deadline:
        try:
            MongoClient(serverSelectionTimeoutMS=3000).admin.command("ping")
            return True
        except Exception:  # noqa: BLE001
            time.sleep(10)
    return False


def execute(command: tuple[str, ...]) -> None:
    import os
    env = dict(os.environ)
    if command[0] == "twse_openapi_sync.py":
        env["LINE_SPOOL"] = str(SPOOL)     # 與原 cron 相同：告警進 digest，不單則推播
    print(f"  ▶ {' '.join(command)}", flush=True)
    result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / command[0]), *command[1:]],
                            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC, env=env)
    for line in result.stdout.strip().splitlines()[-3:]:
        print(f"    {line}")
    if result.returncode != 0:
        raise RuntimeError(f"exit {result.returncode}: {result.stderr.strip()[-120:]}")


def notify(message: str) -> None:
    print(message, flush=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(str(PROJECT_ROOT / ".env"))
        from src.alerts.line_notifier import LineNotifier
        line = LineNotifier()
        if line.enabled:
            line.send(message)
    except Exception as error:  # noqa: BLE001 - 通知失敗不能讓補跑失敗。
        print(f"  LINE 發送失敗：{error}")
    try:
        from src.config import get_db
        from src.domain.collections import COLL_SCHEDULE_ALERTS
        get_db()[COLL_SCHEDULE_ALERTS].insert_one(
            {"ts": datetime.now(), "level": "warning", "source": ALERT_SOURCE, "message": message, "resolved": False})
    except Exception:  # noqa: BLE001
        pass


def repair() -> dict:
    from scripts.data_gap_repair import repair as run_repair
    from src.config import get_db
    return run_repair(get_db(), apply=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只顯示判定的停機時間與將執行的動作，不執行也不通知")
    parser.add_argument("--drill", action="store_true",
                        help="演練：假設停機 30 分鐘，真的執行補抓與缺口回補，結果只印出（不發 LINE、不寫告警）")
    args = parser.parse_args(argv)

    start, previous = boot_start(), previous_boot_end()
    if args.drill:
        previous = start - timedelta(minutes=30)
    gap = downtime.gap(previous, start)
    if args.dry_run:
        will_run = gap is None or gap >= boot_catchup.SHORT_REBOOT
        print(f"boot_start={start:%F %T} previous_boot_end={previous and previous.strftime('%F %T')} "
              f"downtime={downtime.describe(gap)} would_catch_up={will_run}")
        if will_run:
            print("將執行：" + "、".join(c[0] for c in boot_catchup.CATCH_UP_COMMANDS) + "、data_gap_repair --apply")
        return 0

    boot_catchup.run(wait_mongo=wait_mongo, notify=(lambda m: print("【演練】" + m, flush=True)) if args.drill else notify,
                     execute=execute, repair=repair, boot_start=start, previous_boot_end=previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
