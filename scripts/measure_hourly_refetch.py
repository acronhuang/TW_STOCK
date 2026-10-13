#!/usr/bin/env python3
"""量測每小時重抓有沒有價值（OpenSpec evaluate-finmind-sponsor 任務 1.4，量測期間的暫時排程）。

用法：
  python scripts/measure_hourly_refetch.py snapshot    每小時 :50 執行：存下剛被每小時下載碰過的文件的內容雜湊
  python scripts/measure_hourly_refetch.py report      比對相鄰快照，印出每個資料集有多少文件的內容真的變動
只讀 Mongo，只寫 logs/refetch_measure.jsonl。
"""
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ops import refetch_measure as rm  # noqa: E402

OUT = ROOT / "logs" / "refetch_measure.jsonl"
HOURLY_LOGS = ROOT / "logs" / "hourly_updates"


def latest_hourly_log() -> Path | None:
    logs = sorted(HOURLY_LOGS.glob("hourly_update_*.log"))
    return logs[-1] if logs else None


def snapshot(db, now: datetime, out: Path) -> int:
    log = latest_hourly_log()
    codes = rm.hourly_codes(log) if log else set()
    if not codes:
        print("找不到最近一輪每小時下載處理的股票代號，這次不存快照")
        return 1
    since = now - timedelta(minutes=70)
    collections = {}
    for name in rm.COLLECTIONS:
        docs = db[name].find({"stock_id": {"$in": sorted(codes)}, "updated_at": {"$gte": since}})
        collections[name] = {str(doc["_id"]): rm.content_hash(doc) for doc in docs}
    with open(out, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": now.isoformat(), "codes": len(codes), "collections": collections}, ensure_ascii=False) + "\n")
    print(f"快照 {now:%m-%d %H:%M}：{len(codes)} 檔；" + "、".join(f"{k} {len(v)} 筆" for k, v in collections.items()))
    return 0


def run_report(out: Path) -> int:
    snapshots = rm.load_snapshots(out)
    if len(snapshots) < 2:
        print(f"快照只有 {len(snapshots)} 份，至少要 2 份才能比對（需要連續約 24 小時）")
        return 1
    print(f"快照 {len(snapshots)} 份：{snapshots[0]['ts'][:16]} ~ {snapshots[-1]['ts'][:16]}（相鄰兩份比對）")
    for name, row in rm.report(snapshots).items():
        share = f"{row['changed'] / row['compared'] * 100:.2f}%" if row["compared"] else "—（無可比對文件）"
        print(f"{name:24} 被碰過 {row['touched']:>7}  可比對 {row['compared']:>7}  內容有變動 {row['changed']:>5}（{share}）  新出現 {row['new']:>5}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "report"))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    if args.action == "report":
        return run_report(Path(args.out))
    from src.config import get_db
    return snapshot(get_db(), datetime.now(), Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
