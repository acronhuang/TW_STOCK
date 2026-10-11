"""北大市場週期對加權指數的擇時評估：週期建議的曝險，是否優於一直持有大盤。

週期是市場層級的判斷，沒有個股也沒有基準，所以不能走個股帳本的超額報酬模型；
這裡改問「依週期調整曝險，是否勝過買進持有」。純函式，不寫入任何資料。
"""

from dataclasses import dataclass
from datetime import date

from src.backtesting.tw_costs import roundtrip_pct

# suggested_position 的中點（trading_rules.market_cycle 的描述：春 20-30%、夏 50-70%、秋 20-30%、冬 0-10%）。
_EXPOSURE = {"spring": 0.25, "summer": 0.60, "autumn": 0.25, "winter": 0.05}
# 與個股政策的「不同分析日 >= 20」同一個證據不足標準。
MIN_CALLS_PER_CYCLE = 20


@dataclass(frozen=True)
class CycleCall:
    day: date
    cycle: str | None


def cycle_exposure(cycle: str | None) -> float | None:
    return _EXPOSURE.get(cycle) if cycle else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def evaluate_cycle_timing(calls: list[CycleCall], index_closes: dict[date, float], horizon: int, discount: float = 1.0) -> dict:
    """每次呼叫在其後第一個有價日進場、再過 horizon 個有價日出場。

    timed = 曝險 x 指數報酬 - 曝險變動 x 來回成本；第一次呼叫視為從零建倉，不計成本。
    """
    trading_days = sorted(index_closes)
    cost_rate = roundtrip_pct(discount)
    rows = []
    previous_exposure = None
    for call in sorted(calls, key=lambda item: item.day):
        exposure = cycle_exposure(call.cycle)
        if exposure is None:
            continue
        entry_days = [day for day in trading_days if day > call.day]
        if len(entry_days) <= horizon:
            continue  # 沒有足夠的未來價格：不補零。
        entry, exit_ = index_closes[entry_days[0]], index_closes[entry_days[horizon]]
        market_pct = (exit_ / entry - 1) * 100
        turnover = 0.0 if previous_exposure is None else abs(exposure - previous_exposure)
        timed_pct = exposure * market_pct - turnover * cost_rate
        previous_exposure = exposure
        rows.append((call.cycle, market_pct, timed_pct))

    def summarize(items):
        market = [m for _, m, _ in items]
        timed = [t for _, _, t in items]
        edge = [t - m for _, m, t in items]
        return {
            "samples": len(items),
            "mean_buy_hold_pct": _mean(market),
            "mean_timed_pct": _mean(timed),
            "mean_edge_pct": _mean(edge),
        }

    result = summarize(rows)
    result["by_cycle"] = {}
    for cycle in sorted({cycle for cycle, _, _ in rows}):
        part = summarize([row for row in rows if row[0] == cycle])
        part["conclusive"] = part["samples"] >= MIN_CALLS_PER_CYCLE
        result["by_cycle"][cycle] = part
    return result
