"""Collect immutable source evidence without changing prices or strategy eligibility."""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.research_workflow.persistence import DATASETS, capture_finmind, persist_snapshot
from src.research_workflow.registry import canonical, save_new
from src.research_workflow.sources import import_finmind


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--evidence", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.collect and not args.apply:
            print(canonical({"status": "dry_run", "datasets": DATASETS, "requests": len(DATASETS),
                             "database_writes": 0, "certified_complete": False}))
            return 0
        if not args.apply:
            print(canonical(persist_snapshot(args.evidence)))
            return 0
        import fcntl

        load_dotenv(ROOT / ".env")
        (ROOT / "logs").mkdir(exist_ok=True)
        with (ROOT / "logs" / ".quant_source_sync.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            directory = args.evidence
            if args.collect:
                output = args.out or ROOT / "logs" / "quant_source_daily" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                capture_finmind(output / "receipts", os.environ.get("FINMIND_API_TOKEN", ""))
                directory = output / "validated"
                import_finmind(directory, output / "receipts", "1990-01-01",
                               datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat())
            result = persist_snapshot(directory, apply=True)
            if args.collect:
                save_new(output / "sync_result.json", result)
            print(canonical(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, PyMongoError) as exc:
        detail = "database operation failed" if isinstance(exc, PyMongoError) else str(exc)
        print(canonical({"status": "error", "error": type(exc).__name__, "detail": detail}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())