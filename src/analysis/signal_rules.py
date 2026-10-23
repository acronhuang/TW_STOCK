"""候選訊號規則：自行定義、參數事前固定，只用 t 日（含）以前的資料，訊號在 t 日收盤後才知道。

概念來自公開的技術分析（回調結束、回抽、誘空、多方炮、恐慌反包、高位警告、同價位多次受阻、賣出側形態）；
定義與數值是本專案自行決定的，不是任何外部專案的複製，也沒有看過結果後調整。
用途只有驗證實驗（scripts/signal_rules_study.py），不進評分、不進 Hermes 的預測。

輸入 DataFrame 欄位：open、high、low、close（還原價）、volume；索引依日期遞增。
所有運算都是因果的（滾動視窗、正向位移、ewm），tests 以「截斷後重算結果不變」擋前視。
"""

import numpy as np
import pandas as pd

PARAMS = {
    "pullback_band": 0.03,     # 回調結束：收盤與 20 日均線差距上限
    "dryup": 0.7,              # 量比（對前 20 日均量）低於此值算量縮
    "small_body": 1 / 3,       # 止跌 K 線實體占當日振幅上限
    "confirm_vol": 1.2,        # 確認日量比（對前 5 日均量）下限
    "breakout_pct": 0.03,      # 回抽：突破前 60 日高點的幅度
    "breakout_vol": 1.3,
    "touch": 0.01,             # 回踩到原阻力線上下 1% 內
    "throwback_vol": 0.8,
    "throwback_max": 15,       # 突破後最多 15 日內回踩
    "trap_lookback": 20,       # 誘空：前 20 日低點視為支撐
    "trap_vol": 1.5,
    "sandwich_d2_vol": 2.0,
    "sandwich_d3_vol": 1.2,
    "panic_drop": -0.03,
    "panic_vol": 1.5,
    "star_wick": 2.0,          # 流星線：上影線至少為實體的幾倍
    "star_bias": 0.05,         # 高位：最高價高出 10 日指數均線幾成
    "star_ret5": 0.10,         # 或近 5 日漲幅
    "spike_vol": 2.5,
    "stretch_bias": 0.15,
    "nohigh_vol": 0.7,
    "high_window": 20,
    "warn_bias": 0.03,
    "warn_window": 20,
    "warn_block": 5,
    "resist_window": 30,
    "resist_zone": 0.02,
    "resist_wick": 0.015,
    "resist_drop": -0.02,
    "resist_block": 3,
}

ENTRY_RULES = ("pullback_end", "throwback", "bear_trap", "sandwich", "panic_engulf")
SELL_RULES = ("s_trend_turn", "s_shooting_star", "s_volume_spike", "s_stretch", "s_no_volume_high")
FILTER_RULES = ("blk_warn", "blk_resist")  # 對 base（基本入場條件）的過濾器
# 每條規則比較的基準日：premise＝同日上升趨勢中的所有個股；all＝同日所有個股
BASELINE = {**{r: "premise" for r in ENTRY_RULES}, "panic_engulf": "all", **{r: "premise" for r in SELL_RULES}}


def _flag(series):
    return series.fillna(False).astype(bool)


def _shift(series, n):
    return series.shift(n, fill_value=False)


def signals(df, p=PARAMS):
    """回傳 {名稱: 布林 Series}，包含各規則、premise（上升趨勢）、base 與兩個過濾器。"""
    o, h, l, c, v = (df[k].astype(float) for k in ("open", "high", "low", "close", "volume"))
    ma20, ma60 = c.rolling(20).mean(), c.rolling(60).mean()
    ema10 = c.ewm(span=10, adjust=False).mean()
    prev5, prev20 = v.shift(1).rolling(5).mean(), v.shift(1).rolling(20).mean()
    vr5, vr20 = v / prev5.where(prev5 > 0), v / prev20.where(prev20 > 0)
    ret1 = c / c.shift(1) - 1
    body, rng = (c - o).abs(), h - l
    upper, lower = h - np.maximum(c, o), np.minimum(c, o) - l
    above = c > ema10
    uptrend = _flag((c > ma60) & (ma20 > ma60) & (ma60 > ma60.shift(10)))
    out = {"premise": uptrend}

    # ---- 進場側 ----
    candidate = uptrend & ((c / ma20 - 1).abs() <= p["pullback_band"]) & (vr20 < p["dryup"]) & (body <= p["small_body"] * rng)
    confirm = (c > o) & (c > c.shift(1)) & (vr5 > p["confirm_vol"])
    out["pullback_end"] = _flag(_shift(candidate, 1) & confirm)

    level = h.rolling(60).max().shift(1)
    breakout = (c >= level * (1 + p["breakout_pct"])) & (vr5 > p["breakout_vol"])
    confirmed = _shift(breakout, 1) & (c >= level.shift(1) * (1 + p["breakout_pct"]))
    active = level.shift(1).where(confirmed).shift(1).ffill(limit=p["throwback_max"] - 2)
    pullback = (l <= active * (1 + p["touch"])) & (c >= active * (1 - p["touch"])) & (vr5 < p["throwback_vol"])
    out["throwback"] = _flag(_shift(pullback, 1) & (c > o) & (c >= active.shift(1)))

    support = l.rolling(p["trap_lookback"]).min().shift(1)
    broke = (c < support) & (vr5 > p["trap_vol"]) & _shift(uptrend, 1)
    level1, level2 = support.where(broke).shift(1), support.where(broke).shift(2)
    recovered_next = c >= level1
    recovered_later = (c >= level2) & (c.shift(1) < level2)
    out["bear_trap"] = _flag(recovered_next | recovered_later)

    day1 = (c > o) & uptrend
    day2 = (c < o) & (vr5 < p["sandwich_d2_vol"])
    day3 = (c > o) & (vr5 > p["sandwich_d3_vol"]) & (c > c.shift(2))
    out["sandwich"] = _flag(day3 & _shift(day2, 1) & _shift(day1, 2))

    panic = (ret1 <= p["panic_drop"]) & (vr5 > p["panic_vol"])
    out["panic_engulf"] = _flag(_shift(panic, 1) & (c > o) & (vr5 > p["panic_vol"]) & (c >= o.shift(1)))

    # ---- 賣出側 ----
    out["s_trend_turn"] = _flag((~above) & _shift(above, 1) & (c.shift(1) > ma60.shift(1)))
    star = (upper >= p["star_wick"] * body) & (upper >= 0.5 * rng) & (rng > 0)
    high_zone = ((h / ema10 - 1) > p["star_bias"]) | ((c / c.shift(5) - 1) > p["star_ret5"])
    out["s_shooting_star"] = _flag(star & high_zone)
    out["s_volume_spike"] = _flag((vr5 > p["spike_vol"]) & (c < o) & star & uptrend)
    bias = c / ema10 - 1
    out["s_stretch"] = _flag((bias > p["stretch_bias"]) & (bias.shift(1) <= p["stretch_bias"]))
    out["s_no_volume_high"] = _flag((c >= c.rolling(p["high_window"]).max()) & (vr5 < p["nohigh_vol"]))

    # ---- 過濾器（對基本入場條件）----
    out["base"] = _flag(uptrend & above & (ema10 > ema10.shift(5)) & ~((c < o) & (ret1 < -0.015)) & vr5.between(0.3, 2.5))
    hanging = (lower >= 2 * body) & (lower >= 0.5 * rng) & (rng > 0)
    bearish_engulf = (c.shift(1) > o.shift(1)) & (c < o) & (o >= c.shift(1)) & (c <= o.shift(1))
    doji = (rng > 0) & (body <= 0.1 * rng)
    warning = (star | hanging | bearish_engulf | doji) & ((c / ema10 - 1) > p["warn_bias"])
    out["blk_warn"] = _flag(warning.astype(int).rolling(p["warn_window"]).sum() >= p["warn_block"])

    zone = h.rolling(p["resist_window"]).max()
    wick_fail = (h - c) >= p["resist_wick"] * h
    dropped = (c / c.shift(1) - 1) < p["resist_drop"]
    count = pd.Series(0, index=df.index)
    for k in range(p["resist_window"]):
        failed = wick_fail.shift(k, fill_value=False) if k == 0 else wick_fail.shift(k, fill_value=False) | dropped.shift(k - 1, fill_value=False)
        count = count + (failed & (h.shift(k) >= (1 - p["resist_zone"]) * zone)).astype(int)
    out["blk_resist"] = _flag(count >= p["resist_block"])
    return out
