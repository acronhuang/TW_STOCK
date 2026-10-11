#!/usr/bin/env python3
"""資料缺口自動處理：偵測 → 判斷可否回補 → 補 → 驗證 → 登記未補項（data_gap_register）。

偵測沿用 history_continuity_check（以 trading_dates 為交易日曆）。預設 dry-run，--apply 才會回補與寫入。
回補只呼叫既有的按日期工具（皆為冪等 upsert，不刪資料）；來源只給最新日的集合登記為 unrecoverable。
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ReplaceOne  # noqa: E402

from scripts import history_continuity_check as continuity  # noqa: E402
from src.config import get_db  # noqa: E402
from src.data_gap import revenue, runner, valuation  # noqa: E402
from src.data_gap.models import Gap  # noqa: E402
from src.ops.healthcheck import ping  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_DATA_GAP_REGISTER,
    COLL_SCHEDULE_ALERTS,
    COLL_SYSTEM_HEARTBEAT,
)

ALERT_SOURCE = "data_gap_repair"
COMMAND_TIMEOUT_SEC = 900
COMMAND_PAUSE_SEC = 2.0


def detect_gaps(db, window: int, now: datetime):
    """回 (缺口清單, 疑似停市日集合)。日曆準備與 history_continuity_check.main 相同。"""
    calendar = continuity._trading_calendar(db, now.strftime("%Y%m%d"))
    have_price = continuity._date_set(db, "stock_price", continuity._COUNT_FILTER["stock_price"])
    if not have_price:
        return [], frozenset()
    calendar = [day for day in calendar if day >= min(have_price)]
    calendar = calendar[:-continuity.T1_BUFFER][-window:]
    if not calendar:
        return [], frozenset()
    missing = continuity.find_gaps(db, calendar)
    thin = continuity.find_thin_days(db, calendar)
    missing_days = {day for days in missing.values() for day in days}
    closures = continuity._closure_days(db, missing_days) if missing_days else set()
    gaps = [Gap(collection, day, "gap") for collection, days in missing.items() for day in days]
    gaps += [Gap(collection, day, "thin") for collection, rows in thin.items() for day, _, _ in rows]
    gaps += [Gap("stock_factors_valuation", day, "thin") for day in valuation_gap_days(db, calendar)]
    gaps += [Gap("monthly_revenue", revenue.gap_day(month), "thin") for month in revenue_gap_months(db, now)]
    return gaps, frozenset(closures)


def revenue_gap_months(db, now: datetime) -> list[str]:
    """已過法定公告期限（次月 10 日）仍殘缺的月營收月份。"""
    counts = {group["_id"]: group["n"] for group in db["monthly_revenue"].aggregate(
        [{"$group": {"_id": "$year_month", "n": {"$sum": 1}}}])}
    return revenue.thin_months(counts, now.date())


def valuation_gap_days(db, calendar: list[str]) -> list[str]:
    """stock_factors 中官方 PE/PB（TWSE_BWIBBU、TPEX_PERATIO）任一來源殘缺的交易日。"""
    since = datetime.strptime(calendar[0], "%Y%m%d")
    counts: dict[str, dict] = {}
    pipeline = [
        {"$match": {"date": {"$type": "date", "$gte": since}, "data_source": {"$in": sorted(valuation.OFFICIAL_SOURCES)}}},
        {"$group": {"_id": {"day": "$date", "source": "$data_source"}, "n": {"$sum": 1}}},
    ]
    for group in db["stock_factors"].aggregate(pipeline, allowDiskUse=True):
        counts.setdefault(group["_id"]["day"].strftime("%Y%m%d"), {})[group["_id"]["source"]] = group["n"]
    return sorted({day for day, _, _, _ in valuation.thin_days(counts, calendar)})


class MongoRegister:
    def __init__(self, collection):
        self.collection = collection

    def load(self) -> dict:
        return {doc["_id"]: doc for doc in self.collection.find({})}

    def save(self, docs: list[dict]) -> None:
        self.collection.bulk_write([ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs], ordered=False)


def execute_command(command: tuple[str, ...]) -> None:
    script = PROJECT_ROOT / "scripts" / command[0]
    print(f"  ▶ {' '.join(command)}", flush=True)
    result = subprocess.run([sys.executable, str(script), *command[1:]], cwd=str(PROJECT_ROOT),
                            capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC)
    for line in result.stdout.strip().splitlines()[-3:]:
        print(f"    {line}")
    time.sleep(COMMAND_PAUSE_SEC)
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} exit {result.returncode}: {result.stderr.strip()[-160:]}")


def repair(db, *, apply: bool, window: int = 60, max_items: int = 12, max_attempts: int = 3) -> dict:
    now = datetime.now()
    summary = runner.run(
        detect=lambda: detect_gaps(db, window, now),
        execute=execute_command,
        register=MongoRegister(db[COLL_DATA_GAP_REGISTER]),
        alert=lambda message: db[COLL_SCHEDULE_ALERTS].insert_one(
            {"ts": datetime.now(), "level": "warning", "source": ALERT_SOURCE, "message": message, "resolved": False}),
        now=now, apply=apply, max_items=max_items, max_attempts=max_attempts,
    )
    if apply:
        db[COLL_SYSTEM_HEARTBEAT].update_one(
            {"_id": "data_gap_repair"}, {"$set": {"last_run": datetime.now(), "status": "ok", **summary}}, upsert=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="實際回補並寫入登記簿（預設 dry-run）")
    parser.add_argument("--window", type=int, default=60, help="檢查最近 N 個交易日")
    parser.add_argument("--max-items", type=int, default=12, help="單次最多回補幾個缺口")
    parser.add_argument("--max-attempts", type=int, default=3, help="同一缺口最多嘗試次數")
    args = parser.parse_args(argv)

    summary = repair(get_db(), apply=args.apply, window=args.window,
                     max_items=args.max_items, max_attempts=args.max_attempts)
    print(f"detected={summary['detected']} planned={summary['planned']} repaired={summary['repaired']} "
          f"unrecoverable={summary['unrecoverable']} mode={'apply' if args.apply else 'dry-run'}")
    if args.apply:
        # 每日成功才 ping 外部看門狗；整台機器沒開機時外部服務會因「該 ping 沒來」而告警。
        ping(os.getenv("HEALTHCHECK_URL_DATA_GAP"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
