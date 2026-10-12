#!/usr/bin/env python3
"""官方按日期資料同步：零股、盤後定價（上市＋上櫃）、外資 Top20。預設 dry-run，--apply 才寫。

  --date YYYYMMDD            單日（缺口回補用）
  --from YYYYMMDD --to ...   區間（只跑 trading_dates 的交易日）
  --latest                   官方目前最新資料日（排程用；上市先出，上櫃晚到的由下一輪補）
資料日以官方回傳為準，與請求日不符的回應會被丟棄。
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_db  # noqa: E402
from src.data_gap import official_day  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kinds", default="odd,after_hours,foreign_top20", help="逗號分隔：odd,after_hours,foreign_top20")
    parser.add_argument("--date")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--pause", type=float, default=1.2)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    kinds = [k for k in args.kinds.split(",") if k]
    unknown = [k for k in kinds if k not in official_day.SOURCES]
    if unknown:
        parser.error(f"未知類別：{unknown}")

    db = get_db()
    now = datetime.now(timezone.utc)
    total = 0
    for kind in kinds:
        if args.latest:
            days = [official_day.latest_day(kind)]
        elif args.date:
            days = [datetime.strptime(args.date, "%Y%m%d")]
        elif args.start and args.end:
            low, high = (f"{v[:4]}-{v[4:6]}-{v[6:]}" for v in (args.start, args.end))
            days = [datetime.strptime(d["date"], "%Y-%m-%d") for d in
                    db["trading_dates"].find({"date": {"$gte": low, "$lte": high}}).sort("date", 1)]
        else:
            parser.error("需指定 --date、--from/--to 或 --latest")
        for day in filter(None, days):
            docs = official_day.docs_for(kind, day, pause=args.pause)
            markets = {m: sum(1 for d in docs if d.get("market") == m) for m in ("TWSE", "TPEX")}
            print(f"{kind:14} {day:%Y-%m-%d} rows={len(docs)} {markets if kind != 'foreign_top20' else ''}", flush=True)
            if args.apply and docs:
                official_day.upsert(db[official_day.COLLECTION[kind]], docs, now)
            total += len(docs)
            time.sleep(args.pause)
    print(f"rows={total} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
