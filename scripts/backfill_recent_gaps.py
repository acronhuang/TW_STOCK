#!/usr/bin/env python3
"""
回補近期缺漏的交易日資料（隔日自動補昨日缺漏）。

背景：TWSE 三大法人（T86）與本益比/殖利率（BWIBBU）有 T+1 延遲，
當日 17:00 跑 daily 更新時往往尚未公布；若隔天遇週末／連假沒人回頭補，
該交易日就會永久停在「只有股價、缺法人與 PE/PB」的不完整狀態（2026-06-05 事件）。

本腳本掃描近 N 天「有股價但法人或 PE/PB 缺」的『過去』交易日（不含最新一天，
因為最新一天的 T+1 資料本來就還沒公布），逐日呼叫
`twse_daily_update.py --date YYYY-MM-DD` 把整天（股價＋法人＋PE/PB）補齊。
twse_daily_update 為冪等 upsert，且資料未公布時會自動略過，故重複執行安全。

技術因子（RSI/KD/...）不在此處理：daily_senvision.sh [3/4] 會重算近 10 日，會自動跟上。

用法：
    python3 scripts/backfill_recent_gaps.py                 # 預設往回看 7 天
    python3 scripts/backfill_recent_gaps.py --lookback 14
    python3 scripts/backfill_recent_gaps.py --dry-run       # 只報告缺漏，不下載
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pymongo import MongoClient

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

# 判定「該交易日該欄位缺漏」的最低筆數門檻（正常日：法人 ~1224、PE/PB ~1463）。
# 低於門檻 → 視為當天根本沒下載到（非個股零星 null）。
INST_MIN = 100
PERATIO_MIN = 100


def find_incomplete_days(db, lookback: int) -> list[datetime]:
    """回傳近 lookback 天內『有股價、但法人或 PE/PB 缺』的過去交易日（不含最新一天）。"""
    latest_price = db.stock_price.find_one({}, {"date": 1}, sort=[("date", -1)])
    if not latest_price:
        return []
    ref = latest_price["date"]
    since = ref - timedelta(days=lookback)

    # 近 lookback 天有股價的交易日，去掉最新一天（其 T+1 資料本來就還沒公布）
    days = sorted(d for d in db.stock_price.distinct("date", {"date": {"$gte": since}}) if d < ref)

    incomplete = []
    for d in days:
        inst = db.institutional_flow.count_documents({"date": d})
        peb = db.stock_factors.count_documents({"date": d, "pe_ratio": {"$ne": None}})
        missing = []
        if inst < INST_MIN:
            missing.append(f"法人={inst}")
        if peb < PERATIO_MIN:
            missing.append(f"PE/PB={peb}")
        if missing:
            print(f"  缺漏 {d.strftime('%Y-%m-%d')}: " + " ".join(missing))
            incomplete.append(d)
    return incomplete


def backfill_day(day: datetime) -> bool:
    """呼叫 twse_daily_update.py --date 補單一交易日，回傳是否成功執行。"""
    date_str = day.strftime("%Y-%m-%d")
    print(f"  ▶ 回補 {date_str} ...")
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "twse_daily_update.py"), "--date", date_str],
            cwd=str(PROJECT_DIR), capture_output=True, text=True, timeout=300,
        )
        # 只回顯關鍵行，避免洗版
        for line in r.stdout.splitlines():
            if any(k in line for k in ("日期", "新增", "完成", "無資料", "尚未公布")):
                print("    " + line.strip())
        if r.returncode != 0:
            print(f"    ⚠️ twse_daily_update 退出碼 {r.returncode}: {r.stderr.strip()[:200]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"    ⚠️ 回補 {date_str} 逾時")
        return False
    except Exception as e:
        print(f"    ⚠️ 回補 {date_str} 失敗: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="回補近期缺漏交易日（法人 / PE/PB）")
    parser.add_argument("--lookback", type=int, default=7, help="往回掃描天數（預設 7）")
    parser.add_argument("--dry-run", action="store_true", help="只報告缺漏，不實際下載")
    parser.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = parser.parse_args()

    db = MongoClient(args.db_uri)["tw_stock_analysis"]

    days = find_incomplete_days(db, args.lookback)
    if not days:
        print("  ✅ 近期無缺漏交易日，無需回補")
        return

    if args.dry_run:
        print(f"  [DRY RUN] 共 {len(days)} 個缺漏交易日，未執行回補")
        return

    ok = sum(backfill_day(d) for d in days)
    print(f"  回補完成：{ok}/{len(days)} 個交易日")


if __name__ == "__main__":
    main()
