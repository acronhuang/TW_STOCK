#!/usr/bin/env python3
"""訊號規則驗證（唯讀；不寫資料庫、不發通知）。

候選規則的定義與參數固定在 src/analysis/signal_rules.py（寫完才看結果，不調參）；判定標準固定在 src/analysis/signal_study.py。
流程：
  1. dev：2013-06 ~ 2019-12 的訊號。可以看結果、可以修正「實作錯誤」，但不得為了讓結果好看而改規則或參數。
  2. holdout：2020-01 ~ 2026-09 的訊號，只能跑一次（留下 holdout_done.json；要重跑須加 --force-holdout 並在報告註明）。
     並用事前決定的標準判定：開發期與留存期方向都與假設一致，留存期樣本足夠，且在留存期 12 個假設中通過 FDR 10% 檢定。

比較基準：每個有訊號的日子，訊號個股的 t+2..t+21 日累計超額報酬（相對全市場等權指數），減去「同一天、同樣前提條件
（上升趨勢中；恐慌反包則為全部個股）的所有個股」的同窗口平均。訊號收盤後才知道，所以從隔日收盤進場（t+2 起算）；
t+1..t+20 與 t+1..t+5 只當參考。過濾器（高位警告、同價位多次受阻）比較「基本入場條件成立且被過濾」與「成立但未被過濾」。
日內同天的事件先平均成一個值再做 t 檢定（同日個股共享同一天的市場）。

限制（報告一律照列）：資料庫是否含已下市個股會造成存活者偏誤；等權指數含訊號個股自身；未計滑價與流動性衝擊；
12 個假設中即使全無效也預期有 1~2 個偶然顯著，所以看 FDR 結果而不是個別 t 值。

用法：
  python scripts/signal_rules_study.py --split dev [--cache logs/signal_rules/cache.npz] [--limit-symbols N]
  python scripts/signal_rules_study.py --split holdout
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis import signal_rules as sr  # noqa: E402
from src.analysis import signal_study as ss  # noqa: E402

SPLITS = {"dev": (datetime(2013, 6, 1), datetime(2019, 12, 31)), "holdout": (datetime(2020, 1, 1), datetime(2026, 9, 18))}
LOAD_SINCE = datetime(2012, 6, 1)
OUT = ROOT / "logs" / "signal_rules"
MIN_VALUE, MIN_PRICE = 2e7, 10.0  # 近 20 日平均成交值與股價的下限，避開成交稀疏與低價股
MIN_BARS = 130
FIELDS = ("adj_open", "adj_high", "adj_low", "adj_close", "volume", "close")
DIRECTION = {**{r: +1 for r in sr.ENTRY_RULES}, **{r: -1 for r in sr.SELL_RULES}, **{r: -1 for r in sr.FILTER_RULES}}


def to_float(value):
    if value is None:
        return np.nan
    try:
        return float(value.to_decimal()) if hasattr(value, "to_decimal") else float(value)
    except (TypeError, ValueError):
        return np.nan


def load_prices(limit=None, batch=100):
    from src.config import get_db

    db = get_db()
    symbols = sorted(db["stock_price"].distinct("symbol", {"symbol": {"$regex": r"^[1-9]\d{3}$"}}))
    if limit:
        symbols = symbols[:limit]
    dates = sorted(db["stock_price"].distinct("date", {"symbol": "2330", "date": {"$gte": LOAD_SINCE}}))
    row = {d: i for i, d in enumerate(dates)}
    data = {k: np.full((len(dates), len(symbols)), np.nan, dtype=np.float32) for k in FIELDS}
    started = time.time()
    for start in range(0, len(symbols), batch):
        chunk = symbols[start:start + batch]
        column = {s: start + i for i, s in enumerate(chunk)}
        cursor = db["stock_price"].find({"symbol": {"$in": chunk}, "date": {"$gte": LOAD_SINCE}},
                                        {"symbol": 1, "date": 1, **{k: 1 for k in FIELDS}}).batch_size(50000)
        for doc in cursor:
            i = row.get(doc["date"])
            if i is not None:
                j = column[doc["symbol"]]
                for k in FIELDS:
                    data[k][i, j] = to_float(doc.get(k))
        print(f"  載入 {min(start + batch, len(symbols))}/{len(symbols)} 檔，{time.time() - started:.0f} 秒", flush=True)
    return {"dates": np.array(dates, dtype="datetime64[ns]"), "symbols": np.array(symbols), **data}


def get_prices(cache, refresh, limit):
    if cache.exists() and not refresh and not limit:
        loaded = np.load(cache, allow_pickle=False)
        return {k: loaded[k] for k in loaded.files}
    data = load_prices(limit)
    if not limit:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, **data)
    return data


def detect(data):
    close = data["adj_close"]
    days, stocks = close.shape
    names = ["premise", "base", *sr.ENTRY_RULES, *sr.SELL_RULES, *sr.FILTER_RULES]
    masks = {name: np.zeros((days, stocks), dtype=bool) for name in names}
    universe = np.zeros((days, stocks), dtype=bool)
    for j in range(stocks):
        o, h, l, c, v, raw = (data[k][:, j].astype(float) for k in ("adj_open", "adj_high", "adj_low", "adj_close", "volume", "close"))
        valid = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & np.isfinite(v) & (c > 0) & (raw > 0)
        if valid.sum() < MIN_BARS:
            continue
        index = np.nonzero(valid)[0]
        frame = pd.DataFrame({"open": o[index], "high": h[index], "low": l[index], "close": c[index], "volume": v[index]})
        value = (pd.Series(raw[index] * v[index]).rolling(20).mean()).to_numpy()
        universe[index, j] = (value >= MIN_VALUE) & (raw[index] >= MIN_PRICE)
        for name, series in sr.signals(frame).items():
            masks[name][index, j] = series.to_numpy()
    return masks, universe


def coverage(data):
    dates, close = data["dates"], data["adj_close"]
    last = np.array([np.max(np.nonzero(np.isfinite(close[:, j]))[0]) if np.isfinite(close[:, j]).any() else -1 for j in range(close.shape[1])])
    ended = int(np.sum((last >= 0) & (last < len(dates) - 30)))
    return {"symbols": int(close.shape[1]), "days": int(len(dates)), "ended_before_last_30_days": ended,
            "first": str(dates[0])[:10], "last": str(dates[-1])[:10]}


def run_split(split, data, masks, universe, windows):
    start, end = SPLITS[split]
    dates = data["dates"]
    in_range = (dates >= np.datetime64(start)) & (dates <= np.datetime64(end))
    live = universe & in_range[:, None]

    baselines = {}
    for kind, cells in (("premise", masks["premise"] & live), ("all", live)):
        rows, cols = np.nonzero(cells)
        baselines[kind] = {name: ss.day_means(rows, windows.sums(rows, cols, a, b)) for name, (a, b) in ss.WINDOWS.items()}

    results = {}
    for rule in (*sr.ENTRY_RULES, *sr.SELL_RULES):
        rows, cols = ss.dedupe(*np.nonzero(masks[rule] & live))
        results[rule] = {"kind": "rule", "baseline": sr.BASELINE[rule], "events": int(len(rows)), "windows": {}}
        for name, (a, b) in ss.WINDOWS.items():
            values = windows.sums(rows, cols, a, b)
            days, means = ss.day_means(rows, values)
            gap = ss.versus_baseline(rows, values, *baselines[sr.BASELINE[rule]][name])
            results[rule]["windows"][name] = {**gap, "events": int(np.isfinite(values).sum()), "raw_mean": float(means.mean()) if len(means) else float("nan")}
    for rule in sr.FILTER_RULES:
        base = masks["base"] & live
        blocked_rows, blocked_cols = ss.dedupe(*np.nonzero(base & masks[rule]))
        free_rows, free_cols = np.nonzero(base & ~masks[rule])
        results[rule] = {"kind": "filter", "baseline": "base 未被過濾", "events": int(len(blocked_rows)), "windows": {}}
        for name, (a, b) in ss.WINDOWS.items():
            blocked = windows.sums(blocked_rows, blocked_cols, a, b)
            free = windows.sums(free_rows, free_cols, a, b)
            gap = ss.group_gap(blocked_rows, blocked, free_rows, free)
            days, means = ss.day_means(blocked_rows, blocked)
            results[rule]["windows"][name] = {**gap, "events": int(np.isfinite(blocked).sum()), "raw_mean": float(means.mean()) if len(means) else float("nan")}

    names = list(results)
    significant = ss.benjamini_hochberg([results[n]["windows"][ss.PRIMARY]["p"] for n in names])
    for name, flag in zip(names, significant):
        results[name]["fdr_significant"] = bool(flag)
    return results


def pct(value):
    return "  —  " if value is None or not np.isfinite(value) else f"{value * 100:+.2f}%"


def render(split, results, cover):
    lines = [f"# 訊號規則驗證（{split}，{SPLITS[split][0]:%Y-%m-%d} ~ {SPLITS[split][1]:%Y-%m-%d}）",
             f"資料：{cover['symbols']} 檔四位數代號個股、{cover['days']} 個交易日（{cover['first']} ~ {cover['last']}）；"
             f"其中 {cover['ended_before_last_30_days']} 檔在最後 30 個交易日前就沒有價格（若資料庫不含已下市個股，存活者偏誤會讓進場訊號看起來較好）。",
             f"主要窗口 t+{ss.PRIMARY.replace('..', '..t+')} 累計超額報酬；基準＝同日同前提個股的同窗口平均；成本 {ss.COST * 100:.3f}% 只供對照。",
             f"判定標準（事前固定）：兩期方向與假設一致、各期反應日 ≥ {ss.MIN_DAYS} 且事件 ≥ {ss.MIN_EVENTS}、留存期通過 FDR {ss.FDR:.0%}。", "",
             "| 規則 | 假設 | 事件(去重) | 反應日 | 事件日均超額 | 相對基準 | t | p | FDR | 參考 t+1..t+20 | 參考 t+1..t+5 |",
             "|---|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|"]
    for name, item in results.items():
        w = item["windows"][ss.PRIMARY]
        lines.append(f"| {name} | {'正' if DIRECTION[name] > 0 else '負'} | {item['events']} | {w['days']} | {pct(w['raw_mean'])} | {pct(w['mean'])} | "
                     f"{w['t']:.2f} | {w['p']:.3f} | {'是' if item['fdr_significant'] else ''} | "
                     f"{pct(item['windows']['1..20']['mean'])} | {pct(item['windows']['1..5']['mean'])} |")
    return "\n".join(lines)


def summary(results):
    return {name: {"events": item["windows"][ss.PRIMARY]["events"], "days": item["windows"][ss.PRIMARY]["days"],
                   "mean": item["windows"][ss.PRIMARY]["mean"], "t": item["windows"][ss.PRIMARY]["t"],
                   "p": item["windows"][ss.PRIMARY]["p"], "fdr_significant": item["fdr_significant"]} for name, item in results.items()}


def verdicts(dev, hold):
    table = {}
    for name in hold:
        table[name] = ss.decide(dev[name], hold[name], DIRECTION[name], hold[name]["fdr_significant"])
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=sorted(SPLITS), required=True)
    parser.add_argument("--cache", type=Path, default=OUT / "cache.npz")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit-symbols", type=int, default=0)
    parser.add_argument("--force-holdout", action="store_true")
    parser.add_argument("--min-index-stocks", type=int, default=ss.MIN_INDEX_STOCKS, help="等權指數當天至少要有幾檔有價（冒煙測試用）")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    lock, dev_file = OUT / "holdout_done.json", OUT / "result_dev.json"
    if args.split == "holdout":
        if not dev_file.exists():
            sys.exit("尚未有開發期結果（result_dev.json），不能跑留存期。")
        if lock.exists() and not args.force_holdout:
            sys.exit(f"留存期已經跑過（{lock}）；為避免反覆看結果調整，不重跑。若確定要重跑須加 --force-holdout 並在報告註明。")

    data = get_prices(args.cache, args.refresh, args.limit_symbols)
    cover = coverage(data)
    print(f"載入完成：{cover}", flush=True)
    masks, universe = detect(data)
    excess, _ = ss.build_excess(data["adj_close"].astype(float), min_stocks=args.min_index_stocks)
    results = run_split(args.split, data, masks, universe, ss.Windows(excess))
    report = render(args.split, results, cover)
    stamp = datetime.now().strftime("%Y%m%d")
    (OUT / f"report_{args.split}_{stamp}.md").write_text(report, encoding="utf-8")
    payload = {"split": args.split, "generated": datetime.now().isoformat(timespec="seconds"), "coverage": cover,
               "params": sr.PARAMS, "results": summary(results)}
    if args.limit_symbols:
        print(report, "\n（--limit-symbols 只是冒煙測試，不寫結果檔、不算正式結果）")
        return 0
    (OUT / f"result_{args.split}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report)
    if args.split == "holdout":
        dev = json.loads(dev_file.read_text(encoding="utf-8"))["results"]
        table = verdicts(dev, payload["results"])
        lock.write_text(json.dumps({"ran": payload["generated"], "force": args.force_holdout}), encoding="utf-8")
        (OUT / "verdict.json").write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n## 事前標準下的判定\n" + "\n".join(f"- {name}: {verdict}" for name, verdict in table.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
