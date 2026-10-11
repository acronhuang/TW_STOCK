#!/usr/bin/env python3
"""將每日研究訊號擷取為 append-only 成效帳本快照。"""

import argparse
import sys
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RESULTS_DIR, get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE, COLL_TEAM_ANALYSIS  # noqa: E402
from src.research_signal_ledger.benchmark import (  # noqa: E402
    LIQUIDITY_WINDOW_DAYS,
    build_market_benchmark,
    select_liquid_symbols,
)
from src.research_signal_ledger.evaluator import TradingPrice  # noqa: E402
from src.research_signal_ledger.models import CaptureRun  # noqa: E402
from src.research_signal_ledger.repository import ResearchSignalLedgerRepository  # noqa: E402
from src.research_signal_ledger.sources import build_default_sources  # noqa: E402
from src.research_signal_ledger.sources.base import SourceCollectionResult  # noqa: E402


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


ALERT_SOURCE = "research_signal_ledger"
# 帳本啟用時間(台北 naive，對應第一筆 capture run 2026-10-10T13:46Z)。之前完成的 team 結論是歷史回補，
# 依 SDD §2 須另經核准，不得由排程自動帶入。
LEDGER_ACTIVATED_AT = datetime(2026, 10, 10, 21, 46)


def capture_market_benchmark(repository, rows, as_of: str) -> bool:
    analysis_date = _parse_date(as_of)
    prices = [TradingPrice(symbol, _parse_date(trading_date), float(adj_close))
              for symbol, trading_date, adj_close in rows if float(adj_close) > 0]
    if not prices:
        return False
    return repository.insert_benchmark(build_market_benchmark(analysis_date, prices))


def _to_float(value) -> float | None:
    if hasattr(value, "to_decimal"):
        return float(value.to_decimal())
    return float(value) if isinstance(value, (int, float)) else None


def price_day_query(as_of: date) -> dict:
    start = datetime.combine(as_of, time.min)
    return {"date": {"$gte": start, "$lt": start + timedelta(days=1)}}


def benchmark_price_rows(documents, as_of: str):
    rows = []
    for document in documents:
        adj_close = _to_float(document.get("adj_close"))
        if document.get("symbol") and adj_close is not None and adj_close > 0:
            rows.append((document["symbol"], as_of, adj_close))
    return rows


def load_recent_volumes(collection, as_of: date, symbols: list[str]) -> dict[str, list[float]]:
    # 40 個日曆日足以涵蓋 20 個交易日；上界排除 as_of 之後的資料。
    end = datetime.combine(as_of, time.min) + timedelta(days=1)
    query = {"symbol": {"$in": symbols}, "date": {"$gte": end - timedelta(days=41), "$lt": end}}
    dated: dict[str, list[tuple[datetime, float]]] = {}
    for document in collection.find(query, {"symbol": 1, "date": 1, "volume": 1}):
        volume = _to_float(document.get("volume"))
        if volume is not None:
            dated.setdefault(document["symbol"], []).append((document["date"], volume))
    return {
        symbol: [volume for _, volume in sorted(rows, key=lambda row: row[0], reverse=True)][:LIQUIDITY_WINDOW_DAYS]
        for symbol, rows in dated.items()
    }


def liquid_benchmark_rows(database, as_of: date):
    """當日四碼且近 20 日均量達共用門檻的 benchmark 價格列。"""
    collection = database[COLL_STOCK_PRICE]
    rows = benchmark_price_rows(
        collection.find(price_day_query(as_of), {"symbol": 1, "adj_close": 1}), as_of.isoformat()
    )
    four_digit = [symbol for symbol, _, _ in rows if len(symbol) == 4 and symbol.isdigit()]
    liquid = set(select_liquid_symbols(load_recent_volumes(collection, as_of, four_digit)))
    return [row for row in rows if row[0] in liquid]


def recent_trading_dates(collection, as_of: date, count: int) -> list[date]:
    """以 stock_price 實際有資料的日期為準，回傳截至 as_of 的最近 count 個交易日(舊到新)。"""
    upper = datetime.combine(as_of, time.min) + timedelta(days=1)
    dates = {value.date() for value in collection.distinct("date", {"date": {"$lt": upper}})}
    return sorted(dates)[-count:]


def extra_team_batch_dates(
    collection, as_of: date, window_days: int, already: set[date], not_before: datetime | None = None
) -> list[date]:
    """窗口內「才完成」結論所屬、但不在 already 的 team 批次日(舊到新)。

    週五全市場批次約 5 天後才完成，完成時早已超出交易日 lookback。以完成時間(updated_at)篩選而非批次日，
    才能只納入新近完成的結論；帳本啟用前就完成的舊分析屬於歷史回補，不在此列。
    """
    if window_days <= 0:
        return []
    midnight = datetime.combine(as_of, time.min)
    completed_from = midnight - timedelta(days=window_days)
    if not_before is not None:
        completed_from = max(completed_from, not_before)
    query = {
        "updated_at": {"$gte": completed_from},
        "date": {"$lt": midnight + timedelta(days=1)},
        "final_verdict": {"$nin": [None, ""]},
    }
    found = {value.date() for value in collection.distinct("date", query)}
    return sorted(found - already)


def failed_results(results) -> list[SourceCollectionResult]:
    return [result for result in results if result.status == "failed"]


def alert_failed_sources(alerts, failures: list[SourceCollectionResult], now: datetime) -> None:
    """失敗時每次 run 寫一則、24h 去重；全部成功則自動消解舊告警（沿用 verdict_sli 的慣例）。"""
    if not failures:
        alerts.update_many(
            {"source": ALERT_SOURCE, "resolved": {"$ne": True}},
            {"$set": {"resolved": True, "resolved_at": now, "resolved_reason": "auto: capture 全部來源恢復正常"}},
        )
        return
    if alerts.find_one({"source": ALERT_SOURCE, "resolved": {"$ne": True}, "ts": {"$gte": now - timedelta(hours=24)}}):
        return
    detail = "; ".join(f"{result.source}: {result.message or 'failed'}" for result in failures)
    alerts.insert_one(
        {
            "ts": now,
            "level": "warning",
            "source": ALERT_SOURCE,
            "message": f"研究訊號帳本 capture 有 {len(failures)} 個來源失敗（{detail}）。帳本沒有新鮮度審核，這則告警是唯一的如期產生監控。",
            "resolved": False,
        }
    )


def capture_day(database, repository, sources, as_of: date, dry_run: bool) -> list[SourceCollectionResult]:
    """擷取單一資料日；回傳各來源的結果。每個資料日使用獨立 run_id。"""
    run_id = str(uuid.uuid4())
    results: list[SourceCollectionResult] = []
    print(f"== as_of={as_of.isoformat()} ==")
    price_rows = liquid_benchmark_rows(database, as_of)
    if dry_run:
        print(f"market_benchmark would_capture_symbols={len(price_rows)}")
    else:
        benchmark_written = capture_market_benchmark(repository, price_rows, as_of.isoformat())
        print(f"market_benchmark={'captured' if benchmark_written else 'no_output_or_duplicate'}")
    for source in sources:
        try:
            result = source.collect(as_of)
        except Exception as error:  # noqa: BLE001 - source isolation is the CLI contract.
            result = SourceCollectionResult(source.name, [], "failed", str(error)[:1000])
        results.append(result)

        if dry_run:
            if result.status == "captured":
                print(f"{result.source} would_capture={len(result.snapshots)}")
            else:
                print(f"{result.source} status={result.status} {result.message or ''}".rstrip())
            continue

        inserted = 0
        duplicates = 0
        if result.status == "captured":
            write_result = repository.insert_snapshots(result.snapshots)
            inserted = write_result.inserted
            duplicates = write_result.duplicates
        repository.record_capture_run(
            CaptureRun(
                run_id=run_id,
                as_of=as_of,
                source=result.source,
                captured=inserted,
                duplicates=duplicates,
                no_output=1 if result.status == "no_output" else 0,
                unsupported=1 if result.status == "unsupported" else 0,
                failed=1 if result.status == "failed" else 0,
                error_summary=result.message,
                recorded_at=datetime.now(UTC),
            )
        )
        if result.status == "captured":
            print(f"{result.source} captured={inserted} duplicates={duplicates}")
        else:
            print(f"{result.source} status={result.status} {result.message or ''}".rstrip())
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=_parse_date, default=date.today())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--benchmark-only", action="store_true", help="只補當日市場 benchmark，不跑任何來源")
    parser.add_argument("--source", action="append", help="只跑指定來源(可重複)；用於經核准的單一來源回補")
    parser.add_argument(
        "--team-window-days", type=int, default=14,
        help="lookback>1 時，另外納入最近 N 個日曆日內已完成結論的 team 批次日(只跑 team_analysis)；0 停用",
    )
    parser.add_argument(
        "--lookback", type=int, default=1,
        help="回看最近 N 個交易日；各來源的資料日落後不一，排程應用 >1 以補抓遲到的產出(冪等)",
    )
    args = parser.parse_args(argv)
    if args.lookback < 1:
        parser.error("--lookback must be >= 1")
    if args.team_window_days < 0:
        parser.error("--team-window-days must be >= 0")

    database = get_db()
    # dry-run 不得建構 repository，否則會建立 collection 與索引。
    repository = None if args.dry_run else ResearchSignalLedgerRepository(database)
    sources = build_default_sources(database, RESULTS_DIR)
    if args.source:
        unknown = set(args.source) - {source.name for source in sources}
        if unknown:
            parser.error(f"unknown --source: {', '.join(sorted(unknown))}")
        sources = [source for source in sources if source.name in args.source]
    if args.benchmark_only:
        sources = []
    if args.lookback == 1:
        days = [args.as_of]
    else:
        days = recent_trading_dates(database[COLL_STOCK_PRICE], args.as_of, args.lookback)

    all_results: list[SourceCollectionResult] = []
    for day in days:
        all_results.extend(capture_day(database, repository, sources, day, args.dry_run))
    if args.lookback > 1:
        team_sources = [source for source in sources if source.name == "team_analysis"]
        for day in extra_team_batch_dates(
            database[COLL_TEAM_ANALYSIS], args.as_of, args.team_window_days, set(days), LEDGER_ACTIVATED_AT
        ):
            all_results.extend(capture_day(database, repository, team_sources, day, args.dry_run))
    failures = failed_results(all_results)
    if not args.dry_run:
        try:
            alert_failed_sources(database["schedule_alerts"], failures, datetime.now())
        except Exception as error:  # noqa: BLE001 - alerting must never mask the capture result.
            print(f"⚠️ 告警寫入失敗: {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())