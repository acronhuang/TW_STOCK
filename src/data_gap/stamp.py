"""OpenAPI 只給最新已公布交易日的資料；非交易日抓到的資料屬於前一個交易日，不能標成抓取日。"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable


def stamp_day(now: datetime, trading_days: Iterable[str]) -> datetime:
    """trading_days：'YYYY-MM-DD' 字串（trading_dates 集合）。回傳台北午夜的資料日。"""
    today = now.strftime("%Y-%m-%d")
    days = set(trading_days)
    midnight = datetime(now.year, now.month, now.day)
    if today in days:
        return midnight
    earlier = [d for d in days if d < today]
    return datetime.strptime(max(earlier), "%Y-%m-%d") if earlier else midnight
