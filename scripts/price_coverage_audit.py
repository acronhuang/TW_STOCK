#!/usr/bin/env python3
"""價格表覆蓋稽核（唯讀）：官方當日有收盤價的代號，是否都已寫進 stock_price。

用法：python scripts/price_coverage_audit.py [--alert]
有缺漏時以 1 結束；加 --alert 另寫一筆 schedule_alerts（source=price_coverage，相同未處理告警不重複）。
官方來源抓取失敗以 2 結束且不發告警（不是資料缺漏）。排程要放在隔天早上，晚間管線 20:00 才寫入當日價格。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.data_gap.codes import is_price_code
from src.data_gap.coverage import missing_rows


def run(records, db):
    days = sorted({record["date"].date().isoformat() for record in records})
    present = {day: set(db["stock_price"].distinct("symbol", {"date": datetime.fromisoformat(day)})) for day in days}
    gaps = missing_rows(records, present)
    if not gaps:
        return True, f"官方當日有收盤價的 {sum(is_price_code(r['stock_id']) for r in records)} 檔都已在價格表"
    sample = "、".join(code for _, code in gaps[:10])
    return False, f"官方當日有收盤價但價格表沒有 {len(gaps)} 檔（{gaps[0][0]}）：{sample}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alert", action="store_true")
    args = parser.parse_args(argv)
    import twse_daily_update as tdu

    from src.config import get_db

    try:
        records = tdu.fetch_twse() + tdu.fetch_tpex()
    except Exception as exc:  # noqa: BLE001 - 官方來源暫時失敗不等於資料缺漏
        print(f"FAIL 官方行情抓取失敗：{exc}")
        return 2
    db = get_db()
    ok, message = run(records, db)
    print(("OK  " if ok else "FAIL ") + message)
    if ok:
        return 0
    if args.alert:
        from src.ops.alert_dedup import insert_once
        written = insert_once(db["schedule_alerts"], {"ts": datetime.now(), "level": "warning", "source": "price_coverage",
                                                       "message": message, "resolved": False})
        print("[alert] 已寫入 schedule_alerts" if written else "[alert] 已有相同的未處理告警，略過")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
