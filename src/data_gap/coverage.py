from datetime import datetime

from .codes import is_price_code


def missing_rows(records, present):
    """官方當日有收盤價、但 stock_price 沒有該日列的代號。

    records: 官方當日行情（含 stock_id、date）；present: {YYYY-MM-DD: 該日已有列的代號集合}。
    """
    gaps = []
    for record in records:
        code = str(record["stock_id"]).strip()
        if not is_price_code(code):
            continue
        day = record["date"]
        day = day.date().isoformat() if isinstance(day, datetime) else str(day)
        if code not in present.get(day, set()):
            gaps.append((day, code))
    return sorted(gaps)
