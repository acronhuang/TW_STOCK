#!/usr/bin/env python3
"""按日期回補官方殖利率/每股股利 → stock_factors（TWSE BWIBBU_d + TPEX peQryDate）。預設 dry-run。

twse_daily_update 的對應端點只給最新日；停機或漏抓後，歷史日的官方資料只能靠這支補。
只寫官方獨有欄位（殖利率、每股股利、data_source），依 (symbol, date) upsert。PE/PB 不在此寫：
evening_pipeline 的 backfill_pe_pb_factors 每晚用財報重算並覆寫所有 stock_factors 的 PE/PB。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_db  # noqa: E402
from src.data_gap import valuation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    day = datetime.strptime(args.date, "%Y%m%d")
    fetched = valuation.fetch(day)
    for source, rows in fetched.items():
        with_pe = sum(1 for r in rows if r["pe_ratio"] is not None)
        print(f"[{args.date}] {source}: {len(rows)} 檔（含 PE {with_pe}）")
    rows = [r for source_rows in fetched.values() for r in source_rows]
    if not rows:
        print("  上游無資料（非交易日或尚未公布），不寫入")
        return 0
    if not args.apply:
        print("  [DRY-RUN] 未寫入，加 --apply 執行")
        return 0
    result = valuation.upsert(get_db()["stock_factors"], rows, datetime.now())
    print(f"  → 新增 {result.upserted_count}  更新 {result.modified_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
