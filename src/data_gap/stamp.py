"""公告型資料（借券可賣出股數、ETF 定期定額排行、停資停券預告）標的是「適用日」。"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


def applicable_day(now: datetime, trading_days: Iterable[str]) -> datetime:
    """交易日當天適用；非交易日抓到的是下一個交易日的公告。trading_days：'YYYY-MM-DD' 字串。"""
    today = now.strftime("%Y-%m-%d")
    days = set(trading_days)
    midnight = datetime(now.year, now.month, now.day)
    if today in days:
        return midnight
    later = [d for d in days if d > today]
    return datetime.strptime(min(later), "%Y-%m-%d") if later else midnight
