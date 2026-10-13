"""TDD: 公告事件回看的時點判定、累積超額報酬、重複事件、樣本門檻與安慰劑對照。"""

from datetime import datetime, timedelta
import statistics

import pytest

from src.analysis import event_study as es

pytestmark = pytest.mark.unit

START = datetime(2026, 8, 3)
CAL = [START + timedelta(days=n) for n in range(0, 400) if (START + timedelta(days=n)).weekday() < 5]


def day(i):
    return CAL[i]


def flat(jump_at=None, size=0.10):
    """100 元的平盤股票；jump_at 那天起跳高 size。"""
    return {d: (100 * (1 + size) if jump_at is not None and i >= jump_at else 100.0) for i, d in enumerate(CAL)}


MARKET = {d: 1000.0 for d in CAL}


def event(stock, i, when="170000", clause="第12款"):
    return {"stock_id": stock, "day": day(i), "time": when, "clause": clause}


def test_pre_open_and_after_close_and_non_trading_days_start_the_reaction_on_the_right_day():
    assert es.locate(day(10), "083000", CAL) == (10, "ok")      # 開盤前：當天整天算反應
    assert es.locate(day(10), "133000", CAL) == (11, "ok")      # 收盤後：下一交易日
    saturday = day(10) + timedelta(days=2) if day(10).weekday() == 4 else None
    friday = next(i for i in range(5, 40) if CAL[i].weekday() == 4)
    assert es.locate(CAL[friday] + timedelta(days=1), "100000", CAL) == (friday + 1, "ok")  # 週六 → 下週一
    assert saturday is None or es.locate(saturday, "100000", CAL)[1] == "ok"


def test_an_intraday_notice_is_left_out_because_daily_bars_cannot_split_before_and_after():
    assert es.locate(day(10), "103000", CAL) == (None, "intraday")


def test_a_notice_after_the_last_trading_day_has_no_reaction_day_yet():
    assert es.locate(day(len(CAL) - 1), "170000", CAL) == (None, "out_of_range")


def test_the_cumulative_excess_return_catches_the_jump_on_the_reaction_day_only():
    excess = es.daily_excess(flat(jump_at=11), MARKET, CAL)

    assert es.car(excess, 11, 0, 1) == pytest.approx(0.10)
    assert es.car(excess, 11, -5, -1) == pytest.approx(0.0)
    assert es.car(excess, 11, 0, 20) == pytest.approx(0.10)


def test_the_market_is_subtracted():
    market = {d: 1000.0 * (1.01 ** i) for i, d in enumerate(CAL)}  # 大盤每天 +1%
    stock = {d: 100.0 * (1.01 ** i) for i, d in enumerate(CAL)}     # 股票同步
    assert es.car(es.daily_excess(stock, market, CAL), 11, 0, 5) == pytest.approx(0.0)


def test_a_missing_price_is_not_treated_as_zero_it_voids_the_window():
    stock = flat(jump_at=11)
    del stock[day(12)]
    excess = es.daily_excess(stock, MARKET, CAL)

    assert es.car(excess, 11, 0, 1) is None
    assert es.car(excess, 11, -5, -1) == pytest.approx(0.0)


def test_averages_are_withheld_below_the_minimum_event_count():
    stocks = [f"{1000 + n}" for n in range(es.MIN_EVENTS)]
    excess = {s: es.daily_excess(flat(jump_at=11), MARKET, CAL) for s in stocks}

    few = es.study([event(s, 10) for s in stocks[:-1]], excess, CAL)["第12款"]["windows"]["0..1"]
    enough = es.study([event(s, 10) for s in stocks], excess, CAL)["第12款"]["windows"]["0..1"]

    assert few == {"n": es.MIN_EVENTS - 1}
    assert enough["mean"] == pytest.approx(0.10) and enough["share_up"] == 1.0


def test_a_repeat_by_the_same_company_and_clause_within_twenty_days_keeps_only_the_first():
    excess = {"2330": es.daily_excess(flat(jump_at=11), MARKET, CAL)}
    events = [event("2330", 10), event("2330", 15), event("2330", 10, clause="第14款")]

    result = es.study(events, excess, CAL, min_events=1)

    assert result["第12款"]["counts"]["kept"] == 1 and result["第12款"]["counts"]["overlap"] == 1
    assert result["第14款"]["counts"]["kept"] == 1


def test_the_placebo_is_flat_where_the_event_effect_is_not_so_the_control_can_tell_them_apart():
    stocks = [f"{1000 + n}" for n in range(12)]
    excess = {s: es.daily_excess(flat(jump_at=11), MARKET, CAL) for s in stocks}

    out = es.study([event(s, 10) for s in stocks], excess, CAL, min_events=1)["第12款"]

    assert out["windows"]["0..1"]["mean"] == pytest.approx(0.10)
    assert out["placebo"]["0..1"]["mean"] == pytest.approx(0.0)


def test_the_same_seed_gives_the_same_placebo_and_a_different_seed_may_not():
    stocks = [f"{1000 + n}" for n in range(12)]
    excess = {s: es.daily_excess(flat(jump_at=11), MARKET, CAL) for s in stocks}
    events = [event(s, 10) for s in stocks]

    assert es.study(events, excess, CAL, seed=1) == es.study(events, excess, CAL, seed=1)


def test_events_on_the_same_day_count_as_one_day_for_the_t_statistic():
    stocks = [f"{1000 + n}" for n in range(12)]
    excess = {s: es.daily_excess(flat(jump_at=11), MARKET, CAL) for s in stocks}

    out = es.study([event(s, 10) for s in stocks], excess, CAL, min_events=1)["第12款"]["windows"]["0..1"]

    assert out["n"] == 12 and out["days"] == 1 and out["t_day"] is None   # 十二家同日，只算一個獨立的日子


def test_the_day_level_t_statistic_and_the_gap_against_the_placebo():
    sizes = [0.08, 0.09, 0.10, 0.11, 0.12, 0.09, 0.10, 0.11, 0.08, 0.12]
    stocks = [f"{1000 + n}" for n in range(len(sizes))]
    excess = {s: es.daily_excess(flat(jump_at=11 + n, size=size), MARKET, CAL) for n, (s, size) in enumerate(zip(stocks, sizes))}
    events = [event(s, 10 + n) for n, s in enumerate(stocks)]       # 每家各自不同天

    out = es.study(events, excess, CAL, min_events=1)["第12款"]
    expected_t = statistics.fmean(sizes) / (statistics.stdev(sizes) / len(sizes) ** 0.5)

    assert out["windows"]["0..1"]["days"] == len(sizes)
    assert out["windows"]["0..1"]["t_day"] == pytest.approx(expected_t)
    assert out["gap"]["0..1"]["gap"] == pytest.approx(statistics.fmean(sizes)) and out["gap"]["0..1"]["t"] > 5


def test_no_gap_statistic_when_either_side_is_too_small():
    excess = {"2330": es.daily_excess(flat(jump_at=11), MARKET, CAL)}

    assert es.study([event("2330", 10)], excess, CAL)["第12款"]["gap"]["0..1"] is None


def test_the_equal_weight_index_follows_the_average_stock_and_skips_thin_or_broken_days():
    up = {d: 100.0 * (1.01 ** i) for i, d in enumerate(CAL)}     # 每天 +1%
    down = {d: 100.0 * (0.99 ** i) for i, d in enumerate(CAL)}   # 每天 -1%
    glitch = dict(up)
    glitch[CAL[3]] = glitch[CAL[2]] * 2                          # 單日翻倍：資料錯誤，不能拉動指數

    index = es.equal_weight_index({"a": up, "b": down, "c": glitch}, CAL, min_stocks=2)

    assert index[CAL[1]] == pytest.approx(100.0 * (1 + 0.01 / 3))       # 三檔平均 +0.33%
    assert index[CAL[3]] / index[CAL[2]] == pytest.approx(1.0)          # 翻倍那檔被排除，只剩 +1%、-1% 互抵
    assert es.equal_weight_index({"a": up, "b": down}, CAL, min_stocks=3) == {CAL[0]: 100.0}  # 檔數不足就不算


def test_an_event_near_the_end_keeps_the_short_windows_but_loses_the_twenty_day_one():
    last = len(CAL) - 5
    excess = {"2330": es.daily_excess(flat(jump_at=last + 1), MARKET, CAL)}

    out = es.study([event("2330", last)], excess, CAL, min_events=1)["第12款"]["windows"]

    assert out["0..1"]["n"] == 1 and out["0..20"]["n"] == 0
