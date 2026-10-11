"""月營收缺口：法定公告期限是次月 10 日，但 OpenAPI 實測期限過後仍停在舊月份（常在 12 日前後才換月），
所以寬限到 15 日；過了寬限仍殘缺的月份才算缺口（每日 timer 在 10~20 日重抓）。"""
from __future__ import annotations

from datetime import date
from statistics import median

DEADLINE_DAY = 15
THIN_RATIO = 0.9
LOOKBACK_MONTHS = 3


def _shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def gap_day(year_month: str) -> str:
    return year_month.replace("-", "") + "01"


def thin_months(counts: dict[str, int], today: date, ratio: float = THIN_RATIO) -> list[str]:
    """最近三個已過公告期限的月份中，筆數低於前三個月中位數 ratio 倍者。"""
    out = []
    for back in range(1, LOOKBACK_MONTHS + 1):
        year, month = _shift(today.year, today.month, -back)
        next_year, next_month = _shift(year, month, 1)
        if today <= date(next_year, next_month, DEADLINE_DAY):
            continue
        baseline = [counts[label] for label in (_label(*_shift(year, month, -k)) for k in range(1, 4)) if counts.get(label)]
        if baseline and counts.get(_label(year, month), 0) < ratio * median(baseline):
            out.append(_label(year, month))
    return sorted(out)
