"""快照型「最新日」表的真實日期：2026-10-11 以官方按日期資料與清理前備份逐表證實。

- data（資料日）：零股、盤後定價、外資 Top20 —— 交易日 17:30 抓到的是前一交易日的資料，所以標記日要往前一個交易日；
  假日抓到的同樣是上一個交易日的資料。
- applicable（適用日）：借券可賣出股數、ETF 定期定額排行、停資停券預告 —— 公告標的是適用日，交易日標記本來就對，
  假日抓到的是下一個交易日的公告（與下一交易日 17:30 的列 100% 相同）。
"""
from __future__ import annotations

from typing import Iterable

SEMANTICS = {
    "odd_lot_trading": "data", "after_hours_trading": "data", "foreign_top20": "data",
    "securities_lending": "applicable", "etf_dca_rank": "applicable", "margin_suspension": "applicable",
}


def true_day(stamp: str, trading_days: Iterable[str], semantics: str) -> str | None:
    days = set(trading_days)
    if semantics == "data":
        earlier = [d for d in days if d < stamp]
        return max(earlier) if earlier else None
    if stamp in days:
        return stamp
    later = [d for d in days if d > stamp]
    return min(later) if later else None


def day_map(stamped_days: Iterable[str], trading_days: Iterable[str], semantics: str) -> dict[str, str | None]:
    trading = sorted(set(trading_days))
    return {day: true_day(day, trading, semantics) for day in stamped_days}
