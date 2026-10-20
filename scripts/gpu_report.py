#!/usr/bin/env python3
"""依固定小時數（預設 4）分組，列出各節點 GPU 使用率：平均、P90、使用率 >=50% 的時間比例、峰值顯存、缺樣本數。

資料來自 scripts/gpu_sample.py 寫的 logs/gpu_util.csv。
用法：python scripts/gpu_report.py [--hours 4] [--since 2026-10-23] [--until 2026-10-26]
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "logs" / "gpu_util.csv"
NODES = ("28", "27")


def load(path):
    rows = []
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rows.append((datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S"), r["node"],
                         int(r["util_pct"]) if r["util_pct"] else None,
                         int(r["mem_used_mib"]) if r["mem_used_mib"] else None))
    return rows


def bucket_start(t, hours):
    return t.replace(minute=0, second=0, microsecond=0, hour=t.hour // hours * hours)


def summarize(rows, hours=4, since=None, until=None):
    groups = defaultdict(list)
    for t, node, util, mem in rows:
        if (since and t < since) or (until and t >= until):
            continue
        groups[(bucket_start(t, hours), node)].append((util, mem))
    out = {}
    for key, samples in groups.items():
        utils = sorted(u for u, _ in samples if u is not None)
        mems = [m for _, m in samples if m is not None]
        out[key] = {
            "samples": len(utils), "missing": len(samples) - len(utils),
            "mean": sum(utils) / len(utils) if utils else None,
            "p90": utils[int(0.9 * (len(utils) - 1))] if utils else None,
            "busy_pct": sum(1 for u in utils if u >= 50) / len(utils) * 100 if utils else None,
            "max_mem_gib": max(mems) / 1024 if mems else None,
        }
    return out


def fmt(s):
    if not s or s["mean"] is None:
        return f"{'無資料':>30s}"
    return f"{s['mean']:5.0f}% {s['p90']:4d}% {s['busy_pct']:5.0f}% {s['max_mem_gib']:5.1f}G" + (f" 缺{s['missing']}" if s["missing"] else "")


def render(stats, hours=4):
    lines = [f"{'時段':16s} | {'.28 平均 P90 >=50% 顯存':32s} | {'.27 平均 P90 >=50% 顯存':32s}"]
    for b in sorted({k[0] for k in stats}):
        end = b + timedelta(hours=hours)
        lines.append(f"{b:%m-%d %H:00}~{end:%H:00} | {fmt(stats.get((b, '28'))):32s} | {fmt(stats.get((b, '27'))):32s}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=4)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--file", default=str(SRC))
    a = ap.parse_args(argv)
    if not Path(a.file).exists():
        print(f"找不到 {a.file}（scripts/gpu_sample.py 尚未累積資料）")
        return 1
    since = datetime.strptime(a.since, "%Y-%m-%d") if a.since else None
    until = datetime.strptime(a.until, "%Y-%m-%d") if a.until else None
    print(render(summarize(load(a.file), a.hours, since, until), a.hours))
    return 0


if __name__ == "__main__":
    sys.exit(main())
