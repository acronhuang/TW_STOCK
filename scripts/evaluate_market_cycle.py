#!/usr/bin/env python3
"""北大市場週期對加權指數的擇時評估（唯讀報告）。

週期是市場層級的判斷，不是個股訊號，所以不寫進個股帳本。來源是 daily_recommendations.py 每次
落地的 picks_*.json（當時實際產出，不是事後重算），指數用 stock_price 的 TAIEX adj_close。
"""
import argparse
import glob
import json
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RESULTS_DIR, get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE  # noqa: E402
from src.research_signal_ledger.market_cycle import (  # noqa: E402
    MIN_CALLS_PER_CYCLE,
    CycleCall,
    evaluate_cycle_timing,
)

INDEX_SYMBOL = "TAIEX"


def load_cycle_calls(picks_dir: Path) -> list[CycleCall]:
    """每個日曆日取最後一份 picks 的週期；讀不出或沒有週期的檔案略過。"""
    by_day: dict[date, tuple[str, str | None]] = {}
    for path in sorted(glob.glob(str(Path(picks_dir) / "picks_*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            stamp = str(data["date"])
            day = datetime.fromisoformat(stamp).date()
        except (OSError, ValueError, KeyError):
            continue
        cycle = ((data.get("pku") or {}).get("cycle") or {}).get("cycle")
        if not cycle:
            continue
        if day not in by_day or stamp >= by_day[day][0]:
            by_day[day] = (stamp, cycle)
    return [CycleCall(day, cycle) for day, (_, cycle) in sorted(by_day.items())]


def load_index_closes(database) -> dict[date, float]:
    closes = {}
    for document in database[COLL_STOCK_PRICE].find({"symbol": INDEX_SYMBOL}, {"date": 1, "adj_close": 1}):
        value = document.get("adj_close")
        price = float(value.to_decimal()) if hasattr(value, "to_decimal") else value
        day = document["date"].date() if isinstance(document["date"], datetime) else document["date"]
        if isinstance(price, (int, float)) and price > 0:
            closes[day] = float(price)
    return closes


def format_report(horizon: int, result: dict) -> str:
    def pct(value):
        return "n/a" if value is None else f"{value:+.2f}%"

    lines = [
        f"北大市場週期擇時評估（{horizon} 個交易日，扣來回成本，對照一直持有大盤）",
        f"整體：樣本 {result['samples']}，買進持有 {pct(result['mean_buy_hold_pct'])}，"
        f"依週期曝險 {pct(result['mean_timed_pct'])}，差距 {pct(result['mean_edge_pct'])}",
    ]
    for cycle, part in result["by_cycle"].items():
        note = "" if part["conclusive"] else f"  ⚠️證據不足（少於 {MIN_CALLS_PER_CYCLE} 次呼叫）"
        lines.append(
            f"  {cycle:<7} 樣本 {part['samples']:>3}  買進持有 {pct(part['mean_buy_hold_pct'])}  "
            f"依週期 {pct(part['mean_timed_pct'])}  差距 {pct(part['mean_edge_pct'])}{note}"
        )
    lines.append("樣本是逐日重疊的前瞻視窗，彼此高度相關，有效樣本遠少於列出的筆數。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, choices=(5, 10, 20), default=20)
    args = parser.parse_args(argv)

    calls = load_cycle_calls(RESULTS_DIR / "daily_picks")
    closes = load_index_closes(get_db())
    print(format_report(args.horizon, evaluate_cycle_timing(calls, closes, args.horizon)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
