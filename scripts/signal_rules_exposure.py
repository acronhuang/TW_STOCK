#!/usr/bin/env python3
"""s_stretch 風險暴露調整（唯讀；不寫資料庫、不發通知）。事先登記，看任何結果之前寫下。

背景：signal_rules_robustness.py 發現 s_stretch（乖離過大）在各切面都為正，且成交值越大、門檻越高越強。
疑問：這是不是只因為訊號個股剛好有較高的 Beta、波動度、規模或動能暴露？

做法（固定，不隨結果調整）：
  樣本：2013-06-01 ~ 2026-09-18、流動性宇宙內、上升趨勢前提的個股；只用五個暴露都算得出來的格子（三個規格用同一批）。
  每個有事件的日子做一次橫斷面回歸：y＝t+2..t+21 的累計超額報酬；事件＝去重後的訊號（同檔 20 日內只留第一個）；
  控制＝同日、上升趨勢中、近 20 日沒有任何訊號的個股；暴露在當日橫斷面縮尾 1%/99% 後標準化；取事件虛擬變數的係數。
  對各日係數取平均，用 Newey-West（落後 20 日）算 t。
  規格：無控制（對照）；A＝beta、波動度、規模（對數成交值）、中期動能（t−120 到 t−20 報酬）；
        B＝A 加上近 20 日報酬（參考：s_stretch 的定義本身就是短期急漲，控制它會吃掉訊號，所以 B 不用來判定）。
  主要規則：s_stretch；s_no_volume_high 只列出結果當參考（先前切面檢查已顯示不夠一致）。
判定（只針對 s_stretch，規格 A）：平均係數 > 0 且 Newey-West t ≥ 2.0 算「暴露調整後仍存活」，否則「不存活」。
這不是驗證：用的是看過結果才提出假設的同一批資料；真正的驗證仍是 signal_rules_study.py --split forward（2027-03-01 之後）。

用法：python scripts/signal_rules_exposure.py [--cache logs/signal_rules/cache.npz]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import signal_rules_study as study  # noqa: E402
from src.analysis import exposure_adjust as ed  # noqa: E402
from src.analysis import signal_rules as sr  # noqa: E402
from src.analysis import signal_study as ss  # noqa: E402

PERIOD = (datetime(2013, 6, 1), datetime(2026, 9, 18))
RULES = ("s_stretch", "s_no_volume_high")
PRIMARY_RULE = "s_stretch"
ALL = ("beta", "vol", "size", "mom", "short")
SPECS = {"無控制": (), "A": ("beta", "vol", "size", "mom"), "B": ALL}
SURVIVE_T = 2.0


def controls_of(raw_mask, premise, live, recent=ss.DEDUPE_DAYS):
    """上升趨勢中、且近 recent 個交易日（含當天）沒有任何訊號的格子。"""
    count = np.cumsum(raw_mask.astype(np.int32), axis=0)
    prior = count.copy()
    prior[recent:] = count[recent:] - count[:-recent]
    return premise & live & (prior == 0)


def analyze(raw_mask, premise, live, expo, windows, specs=SPECS):
    """回 {規格: {dates, events, gamma, t}}；gamma 是事件相對控制組的窗口超額報酬（已控制該規格的暴露）。"""
    usable = np.all([np.isfinite(expo[k]) for k in ALL], axis=0)
    rows, cols = ss.dedupe(*np.nonzero(raw_mask & live))
    keep = usable[rows, cols]
    rows, cols = rows[keep], cols[keep]
    control = controls_of(raw_mask, premise, live) & usable
    got = {name: {"rows": [], "gammas": [], "events": 0} for name in specs}
    for r in np.unique(rows):
        events, controls = cols[rows == r], np.nonzero(control[r])[0]
        members = np.concatenate([events, controls])
        flag = np.r_[np.ones(len(events)), np.zeros(len(controls))]
        y = windows.sums(np.full(len(members), r), members, *ss.WINDOWS[ss.PRIMARY])
        ok = np.isfinite(y)
        members, flag, y = members[ok], flag[ok], y[ok]
        for name, keys in specs.items():
            X = np.column_stack([expo[k][r, members] for k in keys]) if keys else np.empty((len(members), 0))
            gamma = ed.date_gamma(y, X, flag)
            if gamma is not None:
                got[name]["rows"].append(r)
                got[name]["gammas"].append(gamma)
                got[name]["events"] += int(flag.sum())
    out = {}
    for name, item in got.items():
        mean, t = ed.newey_west_mean_t(item["rows"], item["gammas"])
        out[name] = {"dates": len(item["rows"]), "events": item["events"], "gamma": mean, "t": t}
    return out


def survives(results):
    """事前登記的判定：規格 A 的平均係數 > 0 且 Newey-West t ≥ 2.0。"""
    a = results["A"]
    return bool(np.isfinite(a["gamma"]) and a["gamma"] > 0 and np.isfinite(a["t"]) and a["t"] >= SURVIVE_T)


def build(data):
    """每檔建一次資料表；回 (各規則的訊號矩陣, premise, universe, 成交值)。"""
    days, stocks = data["adj_close"].shape
    masks = {rule: np.zeros((days, stocks), dtype=bool) for rule in RULES}
    premise, universe = np.zeros((days, stocks), dtype=bool), np.zeros((days, stocks), dtype=bool)
    value = np.full((days, stocks), np.nan, dtype=np.float32)
    for j in range(stocks):
        got = study.stock_frame(data, j)
        if got is None:
            continue
        index, frame, average, raw = got
        universe[index, j] = (average >= study.MIN_VALUE) & (raw >= study.MIN_PRICE)
        value[index, j] = average
        signals = sr.signals(frame)
        premise[index, j] = signals["premise"].to_numpy()
        for rule in RULES:
            masks[rule][index, j] = signals[rule].to_numpy()
    return masks, premise, universe, value


def pct(value):
    return "  —  " if value is None or not np.isfinite(value) else f"{value * 100:+.2f}%"


def render(results_by_rule):
    lines = ["# s_stretch 風險暴露調整（不是驗證；看過結果才提出假設的同一批資料）",
             f"期間 {PERIOD[0]:%Y-%m-%d} ~ {PERIOD[1]:%Y-%m-%d}；y＝t+2..t+21 累計超額報酬；規格與判定標準見腳本開頭，結果出來後不更動。", "",
             "| 規則 | 規格 | 日數 | 事件 | 事件相對控制組 | Newey-West t | 相對無控制的保留比例 |", "|---|---|---:|---:|---:|---:|---:|"]
    for rule, results in results_by_rule.items():
        base = results["無控制"]["gamma"]
        for name, item in results.items():
            keep = "—" if name == "無控制" or not np.isfinite(base) or base == 0 else f"{item['gamma'] / base:.0%}"
            t = "—" if not np.isfinite(item["t"]) else f"{item['t']:.2f}"
            lines.append(f"| {rule} | {name} | {item['dates']} | {item['events']} | {pct(item['gamma'])} | {t} | {keep} |")
    verdict = "存活" if survives(results_by_rule[PRIMARY_RULE]) else "不存活"
    lines += ["", f"判定（{PRIMARY_RULE}，規格 A：係數 > 0 且 t ≥ {SURVIVE_T}）：**暴露調整後{verdict}**。",
              "規格 B 與 s_no_volume_high 只當參考。這個判定只回答「是不是單純的風險暴露」，不等於訊號有效。"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=study.OUT / "cache.npz")
    parser.add_argument("--min-index-stocks", type=int, default=ss.MIN_INDEX_STOCKS)
    args = parser.parse_args()
    data = study.get_prices(args.cache, False, 0)
    masks, premise, universe, value = build(data)
    close = data["adj_close"].astype(float)
    excess, market = ss.build_excess(close, min_stocks=args.min_index_stocks)
    expo = ed.exposures(close, excess + market[:, None], market, value)
    dates = data["dates"]
    live = universe & ((dates >= np.datetime64(PERIOD[0])) & (dates <= np.datetime64(PERIOD[1])))[:, None]
    windows = ss.Windows(excess)
    report = render({rule: analyze(masks[rule], premise, live, expo, windows) for rule in RULES})
    study.OUT.mkdir(parents=True, exist_ok=True)
    (study.OUT / f"exposure_{datetime.now():%Y%m%d}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
