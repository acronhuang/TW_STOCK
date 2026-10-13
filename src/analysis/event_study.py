"""公告事件回看：事件前 5 日到後 20 日相對大盤的累積超額報酬。只描述過去，不預測。

規則（皆為避免前視與灌水）：
- 發言在開盤前或非交易日：當天（或下一交易日）整天算反應；收盤後（13:30 起）：下一交易日起算；
  盤中（09:00~13:30）日線分不出公告前後，不納入。
- 報酬以公告前最後一個收盤為基準；缺價的日子不當成 0，含缺價的窗口不計。
- 同公司同款項在 20 個交易日內重複刊登，只留第一則。
- 每款附「安慰劑」對照：同一批公司在其他時間的同樣窗口；有效樣本少於 MIN_EVENTS 不給平均。
"""
import random
import statistics
from bisect import bisect_left
from datetime import datetime

OPEN, CLOSE = "090000", "133000"
WINDOWS = {"前5日": (-5, -1), "0..1": (0, 1), "0..5": (0, 5), "0..20": (0, 20)}
MIN_EVENTS = 8
OVERLAP_DAYS = 20
PLACEBO_OFFSETS = list(range(-90, -29)) + list(range(30, 91))


def locate(day: datetime, when: str, calendar: list[datetime]):
    """回 (day0 在交易日曆的位置, 狀態)；狀態為 ok / intraday / out_of_range。"""
    when = str(when or "").zfill(6)
    idx = bisect_left(calendar, day)
    is_trading = idx < len(calendar) and calendar[idx] == day
    if is_trading:
        if OPEN <= when < CLOSE:
            return None, "intraday"
        if when >= CLOSE:
            idx += 1
    if idx < 1 or idx >= len(calendar):
        return None, "out_of_range"
    return idx, "ok"


def equal_weight_index(series_by_stock: dict, calendar: list[datetime], min_stocks: int = 300,
                       limit: float = 0.12) -> dict:
    """全市場等權指數：當天夠多檔股票有前後兩日價才算，單日漲跌超過 limit 視為資料錯誤而略過。

    市值加權的大盤在小型股落後時會讓『平均超額』整體偏負；等權指數更貼近『一般個股』。
    """
    level, index = 100.0, {calendar[0]: 100.0}
    for i in range(1, len(calendar)):
        today, before = calendar[i], calendar[i - 1]
        moves = [s[today] / s[before] - 1 for s in series_by_stock.values()
                 if today in s and s.get(before) and abs(s[today] / s[before] - 1) <= limit]
        if len(moves) < min_stocks or before not in index:
            continue
        level *= 1 + statistics.fmean(moves)
        index[today] = level
    return index


def daily_excess(stock: dict, market: dict, calendar: list[datetime]) -> list:
    """每個交易日的超額報酬（股票日報酬減大盤日報酬）；任一端缺價的日子為 None。"""
    out = [None] * len(calendar)
    for i in range(1, len(calendar)):
        s0, s1 = stock.get(calendar[i - 1]), stock.get(calendar[i])
        m0, m1 = market.get(calendar[i - 1]), market.get(calendar[i])
        if None in (s0, s1, m0, m1) or 0 in (s0, m0):
            continue
        out[i] = (s1 / s0 - 1) - (m1 / m0 - 1)
    return out


def car(excess: list, day0: int, start: int, end: int):
    lo, hi = day0 + start, day0 + end
    if lo < 1 or hi >= len(excess):
        return None
    window = excess[lo:hi + 1]
    return None if any(v is None for v in window) else sum(window)


def summarize(values: list[float], min_events: int = MIN_EVENTS):
    """有效樣本不足時只回 n，不給平均。"""
    n = len(values)
    if n < min_events:
        return {"n": n}
    return {"n": n, "mean": statistics.fmean(values), "median": statistics.median(values),
            "share_up": sum(v > 0 for v in values) / n}


def _cars(excess: list, day0: int) -> dict:
    return {name: car(excess, day0, a, b) for name, (a, b) in WINDOWS.items()}


def day_means(pairs: list) -> list[float]:
    """同一個反應日的事件先平均成一個值：同日公告的公司共享同一天的市場，不能當成互相獨立。"""
    by_day = {}
    for idx, value in pairs:
        by_day.setdefault(idx, []).append(value)
    return [statistics.fmean(values) for values in by_day.values()]


def _t_stat(values: list[float]):
    if len(values) < 2:
        return None
    spread = statistics.stdev(values)
    return None if spread == 0 else statistics.fmean(values) / (spread / len(values) ** 0.5)


def window_stats(pairs: list, min_events: int) -> dict:
    base = summarize([value for _, value in pairs], min_events)
    if "mean" in base:
        daily = day_means(pairs)
        base |= {"days": len(daily), "t_day": _t_stat(daily)}
    return base


def gap_stats(real: list, fake: list, min_events: int):
    """事件減對照的日群聚 Welch t；任一邊樣本不足或不足兩個反應日就不給。"""
    if len(real) < min_events or len(fake) < min_events:
        return None
    a, b = day_means(real), day_means(fake)
    if len(a) < 2 or len(b) < 2:
        return None
    gap = statistics.fmean(a) - statistics.fmean(b)
    se = (statistics.variance(a) / len(a) + statistics.variance(b) / len(b)) ** 0.5
    return {"gap": gap, "t": gap / se if se else None}


def study(events: list[dict], excess_by_stock: dict, calendar: list[datetime], seed: int = 0,
          min_events: int = MIN_EVENTS) -> dict:
    """events: stock_id、day、time、clause。回傳 {clause: {counts, windows, placebo}}。"""
    rng = random.Random(seed)
    placed = {}
    for ev in events:
        excess = excess_by_stock.get(ev["stock_id"])
        idx, status = locate(ev["day"], ev.get("time"), calendar)
        bucket = placed.setdefault(ev["clause"], {"total": 0, "intraday": 0, "out_of_range": 0,
                                                  "no_price": 0, "overlap": 0, "kept": []})
        bucket["total"] += 1
        if status != "ok":
            bucket[status] += 1
        elif excess is None:
            bucket["no_price"] += 1
        else:
            bucket["kept"].append((ev["stock_id"], idx, excess))

    result = {}
    for clause, bucket in placed.items():
        last_kept, kept = {}, []
        for stock, idx, excess in sorted(bucket["kept"], key=lambda t: (t[0], t[1])):
            if stock in last_kept and idx - last_kept[stock] <= OVERLAP_DAYS:
                bucket["overlap"] += 1
                continue
            last_kept[stock] = idx
            kept.append((stock, idx, excess))
        real = {name: [] for name in WINDOWS}
        fake = {name: [] for name in WINDOWS}
        for stock, idx, excess in kept:
            for name, value in _cars(excess, idx).items():
                if value is not None:
                    real[name].append((idx, value))
            shifted = idx + rng.choice(PLACEBO_OFFSETS)
            if 0 < shifted < len(calendar):
                for name, value in _cars(excess, shifted).items():
                    if value is not None:
                        fake[name].append((shifted, value))
        result[clause] = {
            "counts": {k: bucket[k] for k in ("total", "intraday", "out_of_range", "no_price", "overlap")} | {"kept": len(kept)},
            "windows": {name: window_stats(pairs, min_events) for name, pairs in real.items()},
            "placebo": {name: window_stats(pairs, min_events) for name, pairs in fake.items()},
            "gap": {name: gap_stats(real[name], fake[name], min_events) for name in WINDOWS},
        }
    return result
