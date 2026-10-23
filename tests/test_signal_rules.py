"""TDD: 候選訊號規則——教科書式例子會觸發、差一點的例子不會，且全部只用當日以前的資料。"""

import numpy as np
import pandas as pd
import pytest

from src.analysis import signal_rules as sr

pytestmark = pytest.mark.unit


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], dtype=float)


def rising(n=120, growth=0.002, volume=1000.0):
    c = 100 * (1 + growth) ** np.arange(n)
    o = np.r_[c[0], c[:-1]]
    return bars(list(zip(o, np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996, c, np.full(n, volume))))


def extend(df, *rows):
    return pd.concat([df, bars(list(rows))], ignore_index=True)


def plain(o, c, v=1000.0):
    return (o, max(o, c) * 1.002, min(o, c) * 0.998, c, v)


def fires(df, name):
    sig = sr.signals(df)[name]
    return bool(sig.iloc[-1]) and int(sig.iloc[:-1].sum()) == 0


def silent(df, name):
    return int(sr.signals(df)[name].sum()) == 0


P = rising().close.iloc[-1]


# ---- 回調結束 ----
def pullback(confirm_volume=1500.0, dry_volume=600.0, df=None):
    df = rising() if df is None else df
    p = df.close.iloc[-1]
    candidate = (p, p * 1.0005 * 1.004, p * 0.996, p * 1.0005, dry_volume)
    return extend(df, candidate, plain(candidate[3], candidate[3] * 1.01, confirm_volume))


def test_pullback_end_fires_on_the_confirmation_bar():
    assert fires(pullback(), "pullback_end")


def test_pullback_end_needs_volume_on_the_confirmation_day():
    assert silent(pullback(confirm_volume=900.0), "pullback_end")


def test_pullback_end_needs_the_dry_up_on_the_candidate_day():
    assert silent(pullback(dry_volume=1000.0), "pullback_end")


def test_pullback_end_needs_an_uptrend():
    assert silent(pullback(df=rising(growth=-0.002)), "pullback_end")


# ---- 回抽 ----
def throwback(pull_close=1.012, pull_volume=500.0, gap=0, k_ratio=1.045, s_open=None, s_close=1.03, b_volume=1600.0):
    df = rising()
    p = df.close.iloc[-1]
    level = df.high.iloc[-1]
    b_close, k_close = level * 1.04, level * k_ratio
    rows = [
        (p, b_close * 1.002, p * 0.998, b_close, b_volume),                             # 突破日：放量站上前高 3% 以上
        (b_close, max(b_close, k_close) * 1.002, min(b_close, k_close) * 0.998, k_close, 1000.0),  # 隔日仍在前高 3% 以上
        *[plain(level * 1.03, level * 1.03) for _ in range(gap)],                       # 高位整理的中繼日
        (k_close, k_close * 1.001, level * 1.015, level * 1.02, 800.0),                 # 回落但還沒回到阻力線
        (level * 1.02, level * 1.02, min(level * 1.005, level * pull_close * 0.998), level * pull_close, pull_volume),   # 縮量回踩阻力線
        plain(level * pull_close if s_open is None else level * s_open, level * s_close),   # 阳線再啟動
    ]
    return extend(df, *rows)


def test_throwback_fires_after_a_quiet_retest_of_the_broken_resistance():
    assert fires(throwback(), "throwback")


def test_throwback_is_cancelled_when_the_retest_closes_below_the_old_resistance():
    assert silent(throwback(pull_close=0.97), "throwback")


def test_throwback_needs_the_retest_to_be_on_light_volume():
    assert silent(throwback(pull_volume=2000.0), "throwback")


def test_throwback_only_counts_a_retest_within_fifteen_days_of_the_breakout():
    assert fires(throwback(gap=12), "throwback")   # 突破後第 15 日回踩
    assert silent(throwback(gap=13), "throwback")  # 第 16 日已過期


# ---- 誘空 ----
def trap(break_volume=2000.0, recover_closes=(1.01,), base=None):
    df = rising() if base is None else base
    support = df.low.iloc[-20:].min()
    p = df.close.iloc[-1]
    low_close = support * 0.97
    rows = [(p, p, low_close * 0.995, low_close, break_volume)]
    last = low_close
    for ratio in recover_closes:
        rows.append(plain(last, support * ratio))
        last = support * ratio
    return extend(df, *rows)


def test_bear_trap_fires_when_price_recovers_the_support_the_next_day():
    assert fires(trap(), "bear_trap")


def test_bear_trap_also_fires_on_a_recovery_two_days_later():
    assert fires(trap(recover_closes=(0.98, 1.01)), "bear_trap")


def test_bear_trap_is_not_a_trap_when_price_never_recovers():
    assert silent(trap(recover_closes=(0.98,)), "bear_trap")


def test_bear_trap_needs_the_panic_volume():
    assert silent(trap(break_volume=1000.0), "bear_trap")


def test_bear_trap_needs_the_prior_uptrend():
    assert silent(trap(base=rising(growth=-0.002)), "bear_trap")


def test_bear_trap_fires_once_not_again_while_price_stays_above_the_support():
    sig = sr.signals(trap(recover_closes=(1.01, 1.02)))["bear_trap"]
    assert bool(sig.iloc[-2]) and not sig.iloc[-1] and int(sig.sum()) == 1


# ---- 多方炮 ----
def sandwich(d3_close=1.01, d3_volume=1500.0, d2_volume=1000.0, base=None):
    df = rising() if base is None else base
    p = df.close.iloc[-1]
    c1 = p * 1.01
    c2 = c1 * 0.99
    return extend(df, plain(p, c1), plain(c1, c2, d2_volume), plain(c2, c1 * d3_close, d3_volume))


def test_bullish_sandwich_fires_on_the_third_day():
    assert fires(sandwich(), "sandwich")


def test_bullish_sandwich_needs_day_three_to_close_above_day_one():
    assert silent(sandwich(d3_close=0.995), "sandwich")


def test_bullish_sandwich_needs_volume_on_day_three():
    assert silent(sandwich(d3_volume=1000.0), "sandwich")


def test_bullish_sandwich_rejects_a_heavy_selloff_as_day_two():
    assert silent(sandwich(d2_volume=3000.0, d3_volume=4000.0), "sandwich")


# ---- 恐慌反包 ----
def panic(second_close=1.001, second_volume=2200.0, drop=0.95):
    c0 = P * drop
    return extend(rising(), (P, P, c0 * 0.99, c0, 2000.0), plain(c0, P * second_close, second_volume))


def test_panic_engulf_fires_when_the_next_day_takes_back_the_whole_drop_on_volume():
    assert fires(panic(), "panic_engulf")


def test_panic_engulf_needs_the_close_above_the_panic_days_open():
    assert silent(panic(second_close=0.99), "panic_engulf")


def test_panic_engulf_needs_volume_on_the_second_day():
    assert silent(panic(second_volume=1000.0), "panic_engulf")


def test_panic_engulf_needs_a_real_drop_on_the_panic_day():
    assert silent(panic(drop=0.99), "panic_engulf")


# ---- 賣出側 ----
def test_trend_turn_fires_when_price_falls_below_the_ema_after_an_uptrend_day_above_it():
    assert fires(extend(rising(), (P, P, P * 0.97, P * 0.97, 1000.0)), "s_trend_turn")
    assert silent(extend(rising(), plain(P, P * 1.01)), "s_trend_turn")


def test_shooting_star_needs_a_long_upper_wick_in_a_high_zone():
    assert fires(extend(rising(), (P, P * 1.08, P * 0.999, P * 1.001, 1000.0)), "s_shooting_star")
    assert silent(extend(rising(), (P, P * 1.03, P * 0.999, P * 1.001, 1000.0)), "s_shooting_star")  # 不在高位
    assert silent(extend(rising(), (P, P * 1.0015, P * 0.999, P * 1.001, 1000.0)), "s_shooting_star")  # 沒有長上影


def test_shooting_star_wick_must_be_at_least_twice_the_body():
    # 上影線佔振幅一半以上，但不到實體的兩倍：不算流星線
    assert silent(extend(rising(), (P * 1.07, P * 1.141, P * 1.06, P * 1.10, 1000.0)), "s_shooting_star")


def test_volume_spike_reversal_needs_both_the_volume_and_the_black_candle_with_a_wick():
    assert fires(extend(rising(), (P, P * 1.06, P * 0.994, P * 0.995, 3000.0)), "s_volume_spike")
    assert silent(extend(rising(), (P, P * 1.06, P * 0.994, P * 0.995, 2000.0)), "s_volume_spike")


def test_stretch_fires_only_on_the_first_day_above_the_threshold():
    first = extend(rising(), plain(P, P * 1.20))
    assert fires(first, "s_stretch")
    assert not sr.signals(extend(first, plain(P * 1.20, P * 1.25)))["s_stretch"].iloc[-1]
    assert silent(extend(rising(), plain(P, P * 1.10)), "s_stretch")


def test_new_high_on_thin_volume_is_flagged():
    assert fires(extend(rising(), plain(P, P * 1.002, 600.0)), "s_no_volume_high")
    assert silent(extend(rising(), plain(P, P * 1.002, 900.0)), "s_no_volume_high")


# ---- 基本入場條件與過濾器 ----
def test_base_entry_needs_an_uptrend_and_rejects_a_big_black_candle_or_extreme_volume():
    assert bool(sr.signals(rising())["base"].iloc[-1])
    assert not sr.signals(rising(growth=-0.002))["base"].iloc[-1]
    assert not sr.signals(extend(rising(), plain(P, P * 0.97)))["base"].iloc[-1]
    assert not sr.signals(extend(rising(), plain(P, P * 1.005, 5000.0)))["base"].iloc[-1]


def warnings_frame(stars, jump=1.15, kind="star"):
    df = extend(rising(), plain(P, P * jump))
    last = df.close.iloc[-1]
    for _ in range(stars):
        if kind == "star":
            row = (last, last * 1.03, last * 0.999, last * 1.004, 1000.0)
        elif kind == "hanging":
            row = (last, last * 1.005 * 1.0002, last * 0.97, last * 1.005, 1000.0)
        else:  # doji：實體很小且上下影線各約一半振幅，不同時是流星線或吊頸線
            row = (last, last * 1.0105, last * 0.9905, last * 1.001, 1000.0)
        df = extend(df, row)
        last = df.close.iloc[-1]
    return df


def test_five_high_zone_warning_candles_block_entry_but_four_do_not():
    assert bool(sr.signals(warnings_frame(5))["blk_warn"].iloc[-1])
    assert not sr.signals(warnings_frame(4))["blk_warn"].iloc[-1]


def test_warning_candles_away_from_the_high_zone_do_not_count():
    assert silent(warnings_frame(6, jump=1.0), "blk_warn")


@pytest.mark.parametrize("kind", ["hanging", "doji"])
def test_hanging_man_and_doji_count_as_warning_candles_too(kind):
    assert bool(sr.signals(warnings_frame(5, kind=kind))["blk_warn"].iloc[-1])
    assert not sr.signals(warnings_frame(4, kind=kind))["blk_warn"].iloc[-1]


def engulf_frame(pairs, jump=1.6):
    df = extend(rising(), plain(P, P * jump))
    last = df.close.iloc[-1]
    for _ in range(pairs):
        up_close = last * 1.01
        df = extend(df, plain(last, up_close))
        down_open, down_close = up_close * 1.001, last * 0.999
        df = extend(df, plain(down_open, down_close))
        last = down_close
    return df


def test_bearish_engulfing_counts_as_a_warning_candle():
    assert bool(sr.signals(engulf_frame(5))["blk_warn"].iloc[-1])
    assert not sr.signals(engulf_frame(4))["blk_warn"].iloc[-1]


def resistance_frame(touches, wick=True, trailing=0):
    df = rising()
    top = df.close.iloc[-1] * 1.05
    plain_bar = lambda prev: (prev, top * 0.96, top * 0.95, top * 0.955, 1000.0)
    prev = df.close.iloc[-1]
    rows = []
    for index in range(touches):
        close = top * (0.97 if wick else 0.999)
        rows.append((top * 0.96, top, close * 0.998, close, 1000.0))
        prev = close
        if index < touches - 1 or trailing:
            for _ in range(2 if index < touches - 1 else trailing):
                rows.append(plain_bar(prev))
                prev = top * 0.955
    return extend(df, *rows)


def test_three_failed_touches_of_the_same_zone_block_entry():
    assert bool(sr.signals(resistance_frame(3))["blk_resist"].iloc[-1])
    assert not sr.signals(resistance_frame(2))["blk_resist"].iloc[-1]


def test_a_touch_that_is_sold_off_the_next_day_counts_as_failed_without_a_wick():
    assert bool(sr.signals(resistance_frame(3, wick=False, trailing=1))["blk_resist"].iloc[-1])
    assert not sr.signals(resistance_frame(3, wick=False))["blk_resist"].iloc[-1]  # 最後一次的隔日還沒發生


# ---- 更多負向案例：每個條件都要有測試擋住 ----
def test_pullback_end_needs_a_small_stabilizing_candle():
    df = rising()
    p = df.close.iloc[-1]
    big_body = (p * 0.985, p * 1.002, p * 0.984, p, 600.0)
    assert silent(extend(df, big_body, plain(p, p * 1.01, 1500.0)), "pullback_end")


def test_pullback_end_confirmation_must_close_above_the_previous_close():
    df = pullback()
    candidate_close = df.close.iloc[-2]
    gapped = extend(df.iloc[:-1], (candidate_close * 0.97, candidate_close * 0.992, candidate_close * 0.969, candidate_close * 0.99, 1500.0))
    assert silent(gapped, "pullback_end")


def test_throwback_needs_the_second_close_above_the_breakout_level():
    assert silent(throwback(k_ratio=1.0), "throwback")


def test_throwback_restart_bar_must_close_back_above_the_old_resistance():
    assert silent(throwback(s_open=0.96, s_close=0.985), "throwback")


def test_throwback_needs_the_breakout_day_to_be_on_volume():
    assert silent(throwback(b_volume=1000.0), "throwback")


def test_throwback_restart_bar_must_be_a_white_candle():
    assert silent(throwback(s_open=1.05, s_close=1.03), "throwback")


def test_pullback_end_confirmation_must_be_a_white_candle():
    df = pullback()
    cc = df.close.iloc[-2]
    assert silent(extend(df.iloc[:-1], (cc * 1.03, cc * 1.031, cc * 1.009, cc * 1.01, 1500.0)), "pullback_end")


def test_trend_turn_needs_the_day_before_to_be_above_the_ema():
    two_days = sr.signals(extend(rising(), (P, P, P * 0.97, P * 0.97, 1000.0), (P * 0.97, P * 0.97, P * 0.96, P * 0.96, 1000.0)))["s_trend_turn"]
    assert bool(two_days.iloc[-2]) and not two_days.iloc[-1]  # 第二天仍在均線下方，不是新的轉空


def test_bullish_sandwich_needs_the_uptrend():
    assert silent(sandwich(base=rising(growth=-0.002)), "sandwich")


def test_panic_engulf_rejects_a_black_second_day_even_if_it_closes_above_the_panic_open():
    c0 = P * 0.95
    assert silent(extend(rising(), (P, P, c0 * 0.99, c0, 2000.0), (P * 1.03, P * 1.031, P * 0.999, P * 1.001, 2200.0)), "panic_engulf")


def test_trend_turn_needs_the_prior_day_to_be_in_an_uptrend():
    falling = rising(growth=-0.002)
    f = falling.close.iloc[-1]
    bounce = extend(falling, plain(f, f * 1.04), (f * 1.04, f * 1.04, f * 1.04 * 0.96, f * 1.04 * 0.96, 1000.0))
    assert silent(bounce, "s_trend_turn")


def test_volume_spike_reversal_needs_the_uptrend_and_a_black_candle():
    falling = rising(growth=-0.002)
    f = falling.close.iloc[-1]
    assert silent(extend(falling, (f, f * 1.06, f * 0.994, f * 0.995, 3000.0)), "s_volume_spike")
    assert silent(extend(rising(), (P, P * 1.06, P * 0.999, P * 1.005, 3000.0)), "s_volume_spike")


def test_thin_volume_without_a_new_high_is_not_flagged():
    assert silent(extend(rising(), plain(P, P * 0.99, 600.0)), "s_no_volume_high")


def test_base_entry_rejects_dried_up_volume():
    assert not sr.signals(extend(rising(), plain(P, P * 1.002, 100.0)))["base"].iloc[-1]


# ---- 不得前視 ----
def random_walk(seed=7, n=600):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    return bars(list(zip(o, h, l, c, rng.lognormal(10, 0.5, n))))


def test_every_signal_on_a_prefix_equals_the_same_prefix_of_the_full_series():
    df = random_walk()
    full = sr.signals(df)
    assert sum(int(s.sum()) for s in full.values()) > 50  # 不是全 False 的空測試
    for cut in (250, 400, 599):
        part = sr.signals(df.iloc[:cut])
        for name, series in part.items():
            pd.testing.assert_series_equal(series, full[name].iloc[:cut], check_names=False)


def test_all_outputs_are_boolean_series_aligned_to_the_input():
    df = random_walk(seed=3, n=300)
    out = sr.signals(df)
    expected = {"premise", "base", *sr.ENTRY_RULES, *sr.SELL_RULES, *sr.FILTER_RULES}
    assert set(out) == expected
    assert all(s.dtype == bool and s.index.equals(df.index) for s in out.values())


def test_every_rule_has_a_baseline_and_the_filters_do_not():
    assert set(sr.BASELINE) == set(sr.ENTRY_RULES) | set(sr.SELL_RULES)
    assert set(sr.BASELINE.values()) <= {"premise", "all"}


def test_failed_touches_counts_the_touches_and_drives_the_resistance_filter():
    assert int(sr.failed_touches(resistance_frame(3)).iloc[-1]) == 3
    assert int(sr.failed_touches(resistance_frame(2)).iloc[-1]) == 2
    df = random_walk()
    assert (sr.failed_touches(df) >= sr.PARAMS["resist_block"]).equals(sr.signals(df)["blk_resist"])
