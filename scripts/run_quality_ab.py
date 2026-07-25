#!/usr/bin/env python3
"""v21 quality 因子 A/B —— 三組對照,附選股池覆蓋率防呆。

跑三組(其餘設定相同,皆為修正後行為):
  none        不用 quality(現行基準,年化 16.64%)
  fundamental 財報落後後的真序列(以 available_from 落後)
  legacy      stock_factors 常數(有前視,防呆對照)

🔴 防呆一:選股池 quality 覆蓋率 < 門檻 → 拒跑(否則是選樣偏誤,非因子效果)。
🔴 防呆二:跑完後若 fundamental 的年化 ≈ legacy → 落後機制可能有漏,要重查而非慶祝。

用法:
    python run_quality_ab.py --check        # 只看覆蓋率夠不夠
    python run_quality_ab.py --run           # 覆蓋率達標才跑三組
    python run_quality_ab.py --run --force   # 明知不足也跑(看選樣偏誤長怎樣)
"""
import argparse
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
from pymongo import MongoClient

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
PY = "/home/mdsadmin/Stock/.venv/bin/python"
MIN_COVERAGE = 0.85       # 選股池 quality 覆蓋率門檻


def coverage():
    from src.strategy.multi_factor_strategy import MultiFactorStrategy
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    s = MultiFactorStrategy(db)
    worst = 1.0
    detail = []
    for date in ("2022-06-30", "2023-06-30", "2024-06-28"):
        pool = {p for p in db.stock_factors.distinct(
            "symbol", {"date": datetime.strptime(date, "%Y-%m-%d")})
            if p and len(str(p)) == 4}
        qmap = s._fundamental_quality(date)
        cov = sum(1 for p in pool if p in qmap and qmap[p].get("roe") is not None) / len(pool)
        detail.append((date, len(pool), cov))
        worst = min(worst, cov)
    return worst, detail


def run_one(source):
    print(f"\n{'='*70}\n組別: quality-source = {source}\n{'='*70}", flush=True)
    r = subprocess.run(
        [PY, f"{ROOT}/scripts/backtest_integrated_v21.py",
         "--quality-source", source, "--output", f"/tmp/v21_ab_{source}.json"],
        capture_output=True, text=True, cwd=ROOT, timeout=1800)
    metrics = {}
    for line in r.stdout.splitlines():
        for key in ("年化報酬", "總報酬", "夏普比率", "最大回撤", "勝率"):
            if line.strip().startswith(key):
                parts = line.split()
                if len(parts) >= 3:
                    metrics[key] = parts[1]      # v2.0 欄
    print("  " + "  ".join(f"{k}={v}" for k, v in metrics.items()) or "  (無法解析)")
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    worst, detail = coverage()
    print("選股池 quality 覆蓋率:")
    for d, n, c in detail:
        print(f"  {d}: {n} 檔,覆蓋 {c:.0%}")
    print(f"最低 {worst:.0%}(門檻 {MIN_COVERAGE:.0%})")

    if args.check:
        print("✅ 達標,可跑 A/B" if worst >= MIN_COVERAGE else "⏳ 未達標,再等 fundamental 補跑")
        return

    if not args.run:
        return

    if worst < MIN_COVERAGE and not args.force:
        print(f"\n🔴 覆蓋率 {worst:.0%} < {MIN_COVERAGE:.0%},拒跑(避免選樣偏誤)。"
              "確定要看壞例子請加 --force。")
        return
    if worst < MIN_COVERAGE:
        print(f"\n⚠️ --force:明知覆蓋率 {worst:.0%} 不足仍跑,結果反映選樣偏誤,不可作決策依據。")

    res = {src: run_one(src) for src in ("none", "fundamental", "legacy")}

    print(f"\n{'='*70}\n對照(年化報酬 v2.0 欄)\n{'='*70}")
    for src in ("none", "fundamental", "legacy"):
        print(f"  {src:<12} {res[src].get('年化報酬', '?')}")

    # 防呆二:fundamental ≈ legacy?
    def num(x):
        try:
            return float(str(x).rstrip("%"))
        except (ValueError, AttributeError):
            return None
    f, l = num(res["fundamental"].get("年化報酬")), num(res["legacy"].get("年化報酬"))
    if f is not None and l is not None:
        if abs(f - l) < 1.0:
            print(f"\n🔴 fundamental({f}%) ≈ legacy({l}%) —— 落後機制可能有漏,"
                  "fundamental 疑似吃到前視,須重查 available_from 邏輯,不要當成好結果。")
        else:
            print(f"\n✅ fundamental({f}%) 與 legacy({l}%) 明顯不同,落後機制生效。")


if __name__ == "__main__":
    main()
