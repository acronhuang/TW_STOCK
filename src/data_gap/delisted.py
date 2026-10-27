import re
from datetime import timedelta

STOCK = re.compile(r"[1-9][0-9]{3}")


def plan_history(facts, last_dates, start, grace_days=14):
    """下市 4 碼普通股中，價格表沒有資料或太早結束者 → [{"symbol","from","to"}]。

    facts: [{"symbol","delisted_on"(date)}]；last_dates: {symbol: 最後價格日(date) 或不存在}。
    同一代號有多筆下市事實時略過（代號重用，無法判斷區間）。
    """
    by_symbol = {}
    for fact in facts:
        by_symbol.setdefault(fact["symbol"], []).append(fact["delisted_on"])
    plan = []
    for symbol, stops in sorted(by_symbol.items()):
        if STOCK.fullmatch(symbol) is None or len(stops) != 1 or stops[0] < start:
            continue
        last = last_dates.get(symbol)
        if last is not None and (stops[0] - last).days <= grace_days:
            continue
        plan.append({"symbol": symbol, "from": start if last is None else max(start, last + timedelta(days=1)), "to": stops[0]})
    return plan
