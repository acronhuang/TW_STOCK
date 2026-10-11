"""非交易日被標上資料的列：資料其實是前一個交易日的（抓取日被誤當資料日）。規劃清理動作，不碰資料庫。

證據（2026-10-11，對官方按日期資料比對）：融資融券假日列與官方前一交易日 100% 相同，而交易日 17:30 寫入的列反而是
更前一日的資料；零股假日列與官方 10-08 成交股數 1365/1365 相同，交易日標記列只有 176/1365。因此假日列不能直接刪除，
除非該表有官方按日期資料可以整段覆蓋（目前只有融資融券），其餘一律併入前一交易日。
"""
from __future__ import annotations

from typing import Callable, Iterable

OFFICIAL_REFRESHED = ("margin_purchase_short_sale",)   # 已用官方按日期資料覆蓋，假日列只剩變成多餘的資料
MERGE_KEYS = {"securities_lending": "twse_code", "foreign_top20": "rank", "etf_dca_rank": "rank",
              "margin_suspension": "stock_id", "after_hours_trading": "stock_id", "odd_lot_trading": "stock_id"}
COLLECTIONS = OFFICIAL_REFRESHED + tuple(MERGE_KEYS)


def previous_trading_day(day: str, trading_days: Iterable[str]) -> str | None:
    earlier = [d for d in trading_days if d < day]
    return max(earlier) if earlier else None


def phantom_days(stamped_days: Iterable[str], trading_days: Iterable[str], since: str) -> list[str]:
    trading = set(trading_days)
    return sorted(d for d in set(stamped_days) if d >= since and d not in trading)


def plan(collection: str, days: list[str], trading_days: list[str], rows_at: Callable[[str], int]) -> list[dict]:
    if collection not in COLLECTIONS:
        return []
    filled: set[str] = set()
    actions = []
    for day in sorted(days):
        target = previous_trading_day(day, trading_days)
        if target is None:
            continue
        if rows_at(target) == 0 and target not in filled:
            actions.append({"op": "relabel", "collection": collection, "from": day, "to": target})
            filled.add(target)
        elif collection in OFFICIAL_REFRESHED:
            actions.append({"op": "delete", "collection": collection, "from": day})
        else:
            actions.append({"op": "merge", "collection": collection, "from": day, "to": target,
                            "key": MERGE_KEYS[collection]})
    return actions
