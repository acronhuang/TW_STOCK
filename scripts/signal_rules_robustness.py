#!/usr/bin/env python3
"""s_stretch 與 s_no_volume_high 的穩健性檢查（唯讀；不寫資料庫、不發通知）。

這不是驗證：這兩個現象是看過 2013~2026 的結果之後才提出的，用同一批資料只能問「現象是否在各個切面都一致」，
不能證明它是真的（那要等 signal_rules_study.py --split forward 的新資料）。

切面在看任何結果之前就固定在下面（之後不增不減；想加切面要先改程式並重新提交，那就成了新的檢查）：
  年份：2013 ~ 2026 逐年；成交值：2千萬~1億、1億~5億、5億以上（近 20 日平均）；
  大盤狀態：訊號日前 20 日等權指數累計報酬為正／為負；
  門檻：s_stretch 乖離 10%／20%（原 15%）、s_no_volume_high 量比 0.5／0.9（原 0.7）。
比較基準與主要窗口同 signal_rules_study.py（同日同前提個股、t+2..t+21）。成交值分組時，基準也限定在同一成交值組。
判讀：只看「方向一致的切面比例」與「有沒有顯著為負的切面」，不做通過／不通過的判定。

用法：python scripts/signal_rules_robustness.py [--cache logs/signal_rules/cache.npz]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import signal_rules_study as study  # noqa: E402
from src.analysis import signal_rules as sr  # noqa: E402
from src.analysis import signal_study as ss  # noqa: E402

PERIOD = (datetime(2013, 6, 1), datetime(2026, 9, 18))
RULES = ("s_stretch", "s_no_volume_high")
VARIANTS = {"s_stretch": ("stretch_bias", (0.10, 0.20)), "s_no_volume_high": ("nohigh_vol", (0.5, 0.9))}
LIQUIDITY = (("成交值 2千萬~1億", 2e7, 1e8), ("成交值 1億~5億", 1e8, 5e8), ("成交值 5億以上", 5e8, float("inf")))
STATE_WINDOW = 20
MIN_SLICE_DAYS = 20  # 反應日少於這個數的切面只列出，不納入「方向一致」的計數


def market_state(market, window=STATE_WINDOW):
    """回 (前 window 日等權指數累計報酬是否為正, 是否有足夠歷史)；含訊號日當天收盤，訊號日收盤後就知道。"""
    csum = np.cumsum(np.nan_to_num(market))
    trailing = csum.copy()
    trailing[window:] = csum[window:] - csum[:-window]
    return trailing > 0, np.arange(len(market)) >= window


def baseline_of(cells, windows):
    rows, cols = np.nonzero(cells)
    return ss.day_means(rows, windows.sums(rows, cols, *ss.WINDOWS[ss.PRIMARY]))


def evaluate(rows, cols, windows, baseline):
    values = windows.sums(rows, cols, *ss.WINDOWS[ss.PRIMARY])
    return {"events": int(np.isfinite(values).sum()), **ss.versus_baseline(rows, values, *baseline)}


def variant_labels(rule):
    name, values = VARIANTS[rule]
    return [(f"{rule} {name}={v:g}", {**sr.PARAMS, name: v}) for v in values]


def build_masks(data):
    """每檔只建一次資料表；對基準參數與各門檻變體各算一次訊號。回 (masks, premise, universe, value)。"""
    days, stocks = data["adj_close"].shape
    plan = {rule: (rule, sr.PARAMS) for rule in RULES}
    for rule in RULES:
        plan.update({label: (rule, params) for label, params in variant_labels(rule)})
    masks = {label: np.zeros((days, stocks), dtype=bool) for label in plan}
    premise, universe = np.zeros((days, stocks), dtype=bool), np.zeros((days, stocks), dtype=bool)
    value = np.full((days, stocks), np.nan, dtype=np.float32)
    for j in range(stocks):
        got = study.stock_frame(data, j)
        if got is None:
            continue
        index, frame, average, raw = got
        universe[index, j] = (average >= study.MIN_VALUE) & (raw >= study.MIN_PRICE)
        value[index, j] = average
        for position, (label, (rule, params)) in enumerate(plan.items()):
            signals = sr.signals(frame, params)
            masks[label][index, j] = signals[rule].to_numpy()
            if position == 0:
                premise[index, j] = signals["premise"].to_numpy()
    return masks, premise, universe, value


def slices_for(rule, masks, premise, live, value, windows, dates, market):
    """回 [(切面名稱, 結果 dict)]；事件先以全期間去重，再依切面篩選。"""
    positive, enough = market_state(market)
    baseline = baseline_of(premise & live, windows)
    rows, cols = ss.dedupe(*np.nonzero(masks[rule] & live))
    out = [("全期間", evaluate(rows, cols, windows, baseline))]
    years = dates[rows].astype("datetime64[Y]").astype(int) + 1970
    for year in sorted(set(years.tolist())):
        keep = years == year
        out.append((f"{year} 年", evaluate(rows[keep], cols[keep], windows, baseline)))
    traded = value[rows, cols]
    for name, low, high in LIQUIDITY:
        keep = (traded >= low) & (traded < high)
        band = baseline_of(premise & live & (value >= low) & (value < high), windows)
        out.append((name, evaluate(rows[keep], cols[keep], windows, band)))
    for name, want in (("大盤前 20 日為正", True), ("大盤前 20 日為負", False)):
        keep = enough[rows] & (positive[rows] == want)
        out.append((name, evaluate(rows[keep], cols[keep], windows, baseline)))
    for label, _ in variant_labels(rule):
        r, c = ss.dedupe(*np.nonzero(masks[label] & live))
        out.append((label.split(" ", 1)[1], evaluate(r, c, windows, baseline)))
    return out


def summarize(slices):
    """只看方向一致的切面比例與顯著為負的切面；反應日太少的切面不納入計數。"""
    usable = [(name, s) for name, s in slices[1:] if s["days"] >= MIN_SLICE_DAYS and np.isfinite(s["mean"])]
    positive = [name for name, s in usable if s["mean"] > 0]
    negative = [name for name, s in usable if s["mean"] < 0 and np.isfinite(s["t"]) and s["t"] <= -2]
    return {"usable": len(usable), "positive": len(positive), "significantly_negative": negative,
            "skipped": [name for name, s in slices[1:] if s["days"] < MIN_SLICE_DAYS or not np.isfinite(s["mean"])]}


def pct(value):
    return "  —  " if value is None or not np.isfinite(value) else f"{value * 100:+.2f}%"


def render(rule, slices):
    summary = summarize(slices)
    lines = [f"## {rule}", "", "| 切面 | 事件 | 反應日 | 相對基準 | t |", "|---|---:|---:|---:|---:|"]
    for name, s in slices:
        t = "—" if not np.isfinite(s["t"]) else f"{s['t']:.2f}"
        lines.append(f"| {name} | {s['events']} | {s['days']} | {pct(s['mean'])} | {t} |")
    lines.append("")
    lines.append(f"方向為正的切面 {summary['positive']}/{summary['usable']}（不含全期間，且反應日 ≥ {MIN_SLICE_DAYS}）；"
                 f"顯著為負（t ≤ -2）的切面：{'、'.join(summary['significantly_negative']) or '無'}"
                 + (f"；樣本太少未計入：{'、'.join(summary['skipped'])}" if summary["skipped"] else ""))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=study.OUT / "cache.npz")
    parser.add_argument("--min-index-stocks", type=int, default=ss.MIN_INDEX_STOCKS)
    args = parser.parse_args()
    data = study.get_prices(args.cache, False, 0)
    masks, premise, universe, value = build_masks(data)
    excess, market = ss.build_excess(data["adj_close"].astype(float), min_stocks=args.min_index_stocks)
    windows = ss.Windows(excess)
    dates = data["dates"]
    live = universe & ((dates >= np.datetime64(PERIOD[0])) & (dates <= np.datetime64(PERIOD[1])))[:, None]
    parts = ["# 穩健性檢查（不是驗證；看過結果才提出的現象，不能用同一批資料證明）",
             f"期間 {PERIOD[0]:%Y-%m-%d} ~ {PERIOD[1]:%Y-%m-%d}；切面與判讀方式見腳本開頭，結果出來後不增減切面。", ""]
    for rule in RULES:
        parts += [render(rule, slices_for(rule, masks, premise, live, value, windows, dates, market)), ""]
    report = "\n".join(parts)
    study.OUT.mkdir(parents=True, exist_ok=True)
    (study.OUT / f"robustness_{datetime.now():%Y%m%d}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
