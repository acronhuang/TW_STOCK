#!/usr/bin/env python3
"""財報重編版本快照：比對 quarterly_earnings 與 quarterly_earnings_versions，保存被改動前的舊版。預設 dry-run，--apply 才寫。

首次執行會替每個季度建立 baseline（v1）；之後每日執行，既有數值被改動才新增版本並告警。
時點查詢請用 src.fundamentals.restatement.version_as_of。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import ASCENDING, UpdateOne  # noqa: E402

from src.config import get_db  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_QUARTERLY_EARNINGS,
    COLL_QUARTERLY_EARNINGS_VERSIONS,
    COLL_SCHEDULE_ALERTS,
    COLL_SYSTEM_HEARTBEAT,
)
from src.fundamentals import restatement  # noqa: E402

BATCH = 1000
PROJECTION = {"_id": 0, "symbol": 1, "year": 1, "season": 1, "report_type": 1, "data_source": 1,
              "income": 1, "balance": 1, "cashflow": 1}


def latest_hashes(versions) -> dict:
    pipeline = [
        {"$sort": {"symbol": 1, "year": 1, "season": 1, "version": -1}},
        {"$group": {"_id": {"s": "$symbol", "y": "$year", "q": "$season"},
                    "version": {"$first": "$version"}, "hash": {"$first": "$content_hash"}}},
    ]
    return {(g["_id"]["s"], g["_id"]["y"], g["_id"]["q"]): (g["version"], g["hash"])
            for g in versions.aggregate(pipeline, allowDiskUse=True)}


def write(versions, actions: list[dict]) -> None:
    inserts = [a["doc"] for a in actions if a["op"] == "insert"]
    for start in range(0, len(inserts), BATCH):
        versions.insert_many(inserts[start:start + BATCH], ordered=False)
    merges = [UpdateOne({"_id": a["id"]}, {"$set": a["set"]}) for a in actions if a["op"] == "merge"]
    for start in range(0, len(merges), BATCH):
        versions.bulk_write(merges[start:start + BATCH], ordered=False)


def alert_restated(db, actions: list[dict], summary: dict, now: datetime) -> None:
    restated = [a["doc"] for a in actions if a["op"] == "insert" and not a["doc"]["baseline"]]
    if not restated:
        return
    same_source = sum(1 for d in restated if not d.get("source_changed"))
    examples = "、".join(f"{d['symbol']} {d['year']}Q{d['season']}({d['changed_fields'][0]})" for d in restated[:5])
    db[COLL_SCHEDULE_ALERTS].insert_one({
        "ts": now, "level": "info", "source": "financial_restatement", "resolved": False,
        "message": f"財報數字被改動 {len(restated)} 筆（同來源 {same_source} 筆，換來源 {len(restated) - same_source} 筆）：{examples}",
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    quarterly, versions = db[COLL_QUARTERLY_EARNINGS], db[COLL_QUARTERLY_EARNINGS_VERSIONS]
    now = datetime.now()
    if args.apply:
        versions.create_index([("symbol", ASCENDING), ("year", ASCENDING), ("season", ASCENDING), ("version", ASCENDING)],
                              unique=True, name="uq_quarter_version")

    def load_latest(key):
        return versions.find_one({"symbol": key[0], "year": key[1], "season": key[2]}, sort=[("version", -1)])

    actions, summary = restatement.build_actions(
        quarterly.find({}, PROJECTION).batch_size(2000), latest_hashes(versions), load_latest, now)
    print(f"baseline={summary['baseline']} restated={summary['restated']} merged={summary['merged']} "
          f"unchanged={summary['unchanged']} mode={'apply' if args.apply else 'dry-run'}")
    if args.apply:
        write(versions, actions)
        alert_restated(db, actions, summary, now)
        db[COLL_SYSTEM_HEARTBEAT].update_one(
            {"_id": "financial_versions"}, {"$set": {"last_run": now, "status": "ok", **summary}}, upsert=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
