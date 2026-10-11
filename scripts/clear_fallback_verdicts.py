#!/usr/bin/env python3
"""清除 Ollama 全失敗後被寫成結論的預設「持有」（先備份原值）。預設 dry-run，--apply 才寫入。"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.moe.retry import is_fallback_verdict  # noqa: E402


def clear_fallback_verdicts(collection, backup_path: Path, apply: bool, since: datetime, now: datetime) -> list[dict]:
    query = {"date": {"$gte": since}, "final_verdict": {"$nin": [None, ""]}, "consensus.n": 0}
    targets = [
        document for document in collection.find(query, {"symbol": 1, "date": 1, "final_verdict": 1, "advisor": 1,
                                                          "consensus": 1, "updated_at": 1})
        if is_fallback_verdict(document)
    ]
    if apply and targets:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with backup_path.open("w", encoding="utf-8") as handle:
            for document in targets:
                handle.write(json.dumps({
                    "_id": str(document["_id"]), "symbol": document["symbol"], "date": document["date"].isoformat(),
                    "final_verdict": document["final_verdict"], "updated_at": document["updated_at"].isoformat(),
                }, ensure_ascii=False) + "\n")
        # 不動 updated_at：它是結論可用時間，帳本與驗證都靠它。
        collection.update_many(
            {"_id": {"$in": [document["_id"] for document in targets]}},
            {"$set": {"final_verdict": None, "ollama_failed": True, "verdict_cleared_at": now}},
        )
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=datetime.fromisoformat, default=datetime(2026, 9, 1))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=PROJECT_ROOT / "backups" / "fallback_verdicts")
    args = parser.parse_args(argv)

    from src.config import get_db

    now = datetime.now()
    backup = args.backup_dir / f"fallback_verdicts_{now:%Y%m%d_%H%M%S}.jsonl"
    targets = clear_fallback_verdicts(get_db()["team_analysis"], backup, args.apply, args.since, now)
    by_day: dict[str, int] = {}
    for document in targets:
        by_day[document["date"].strftime("%Y-%m-%d")] = by_day.get(document["date"].strftime("%Y-%m-%d"), 0) + 1
    print(f"{'cleared' if args.apply else 'would_clear'}={len(targets)} by_date={dict(sorted(by_day.items()))}")
    if args.apply and targets:
        print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
