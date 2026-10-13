#!/usr/bin/env python3
"""上櫃、興櫃（以及上市對帳）重大訊息：以 MOPS 按日期清單對帳並補洞，缺的列再抓明細全文。預設 dry-run，--apply 才寫入。

用法：
  mops_major_sync.py --days 3                          # 每日對帳：今天起往前 3 天，只統計缺幾筆
  mops_major_sync.py --days 3 --apply                  # 補寫缺的列（含全文）
  mops_major_sync.py --from 20260714 --to 20261012 --markets otc,rotc --apply   # 歷史回補（可中斷續跑）
清單沒有的不會寫、明細失敗的列不寫入，下次執行仍會當作缺而重試，所以任何時候中斷重跑都安全。
MOPS 無公開速率說明，預設每次呼叫間隔 0.7 秒。
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402
from pymongo import ASCENDING  # noqa: E402

from src.config import get_db  # noqa: E402
from src.data_gap import mops_major as mm  # noqa: E402
from src.utils.circuit_breaker import CircuitBreaker, CircuitOpen  # noqa: E402

BASE = "https://mops.twse.com.tw/mops/api"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://mops.twse.com.tw/", "Content-Type": "application/json"}


class Mops:
    def __init__(self, pause: float):
        self.session = requests.Session()
        self.pause = pause
        self.breakers = {}  # 每個端點一個斷路器：MOPS 掛掉時不要每筆都等逾時加重試

    def post(self, endpoint: str, payload: dict) -> dict:
        breaker = self.breakers.setdefault(endpoint, CircuitBreaker(failure_threshold=4, cooldown=300.0))
        if not breaker.allow():
            raise CircuitOpen(f"{endpoint} 連續失敗，斷路器開啟中，暫不送出")
        last = None
        for attempt in range(3):
            try:
                response = self.session.post(f"{BASE}/{endpoint}", json=payload, headers=HEADERS, timeout=60)
                response.raise_for_status()
                time.sleep(self.pause)
                data = response.json()
                breaker.success()
                return data
            except Exception as error:  # noqa: BLE001
                last = error
                time.sleep(2 * (attempt + 1))
        breaker.failure()
        raise RuntimeError(f"{endpoint} 連續失敗: {last}")

    def day_list(self, day: datetime) -> dict:
        return self.post("t05st02", {"year": str(day.year - 1911), "month": f"{day.month:02d}", "day": f"{day.day:02d}"})

    def detail(self, params: dict) -> dict:
        return self.post("t05st02_detail", params)


def run_day(db, mops: Mops, day: datetime, markets: tuple[str, ...], apply: bool) -> dict:
    payload = mops.day_list(day)
    rows = mm.parse_list(payload)
    if not rows and payload.get("code") != 200:
        raise RuntimeError(f"{day:%Y-%m-%d} 清單回應異常: {payload.get('code')} {payload.get('message')}")
    existing = list(db["major_news"].find({"date": {"$gte": day - timedelta(days=1), "$lte": day}},
                                          {"stock_id": 1, "date": 1, "time": 1, "subject": 1}))
    keys = mm.existing_keys(existing)
    per_market = {m: mm.coverage(mm.only_markets(rows, (m,)), keys) for m in markets}
    result = mm.reconcile(rows, keys, markets, mops.detail if apply else None, datetime.now())
    if apply and result["docs"]:
        mm.save_new(db["major_news"], result["docs"])
    stats = {"day": day.strftime("%Y-%m-%d"), "markets": {m: {"official": a, "held": b} for m, (a, b) in per_market.items()},
             "missing": result["missing"], "filled": len(result["docs"]), "failed": result["failed"], "applied": apply}
    if apply:
        db["mops_reconcile_log"].insert_one({**stats, "ts": datetime.now()})
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", help="YYYYMMDD")
    parser.add_argument("--to", dest="end", help="YYYYMMDD")
    parser.add_argument("--days", type=int, default=3, help="未指定 --from 時，對帳今天起往前幾天")
    parser.add_argument("--markets", default="sii,otc,rotc")
    parser.add_argument("--pause", type=float, default=0.7)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    markets = tuple(m.strip() for m in args.markets.split(",") if m.strip())
    unknown = [m for m in markets if m not in mm.LISTED_MARKETS]
    if unknown:
        parser.error(f"不支援的市場別: {unknown}（可用 {list(mm.LISTED_MARKETS)}）")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if args.start:
        first = datetime.strptime(args.start, "%Y%m%d")
        last = datetime.strptime(args.end, "%Y%m%d") if args.end else today
    else:
        first, last = today - timedelta(days=args.days - 1), today
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]

    db = get_db()
    db["major_news"].create_index([("stock_id", ASCENDING), ("date", ASCENDING)])
    mops = Mops(args.pause)
    errors = failed = filled = 0
    for day in days:
        try:
            stats = run_day(db, mops, day, markets, args.apply)
        except Exception as error:  # noqa: BLE001
            errors += 1
            print(f"{day:%Y-%m-%d} 失敗: {str(error)[:120]}", flush=True)
            continue
        failed += stats["failed"]
        filled += stats["filled"]
        held = " ".join(f"{m}:{v['held']}/{v['official']}" for m, v in stats["markets"].items())
        print(f"{stats['day']} 官方/已有 {held} 缺 {stats['missing']} 補 {stats['filled']} 明細失敗 {stats['failed']}"
              f"{'' if args.apply else ' (dry-run)'}", flush=True)
    print(f"完成：{len(days)} 天，補寫 {filled} 筆，明細失敗 {failed}，清單失敗 {errors} 天，mode={'apply' if args.apply else 'dry-run'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
