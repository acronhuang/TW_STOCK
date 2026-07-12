#!/usr/bin/env python3
"""
把 results/team_analysis/team_*.json 灌入 MongoDB team_analysis 集合。
可重複執行（upsert，依 symbol+date）；保留既有 verify 欄位與 created_at。

用法:
  migrate_team_to_db.py             dry-run（只報告）
  migrate_team_to_db.py --apply     實際寫入
  migrate_team_to_db.py --apply --date 20260710   只灌單一日期
"""
import glob
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from src.moe.team_store import ensure_indexes, get_db, upsert_analyses

DIR = "/home/mdsadmin/Stock/tw-stock-analysis/results/team_analysis"
APPLY = "--apply" in sys.argv
ONLY = None
if "--date" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--date") + 1]


def date_from_name(fn: str):
    m = re.search(r"team_(\d{8})", os.path.basename(fn))
    return datetime.strptime(m.group(1), "%Y%m%d") if m else None


def main():
    db = get_db()
    if APPLY:
        ensure_indexes(db)
    files = sorted(glob.glob(f"{DIR}/team_*.json"))
    total_up, total_mod, total_docs = 0, 0, 0
    for f in files:
        d = date_from_name(f)
        if d is None:
            continue
        if ONLY and d.strftime("%Y%m%d") != ONLY:
            continue
        data = json.load(open(f, encoding="utf-8"))
        if isinstance(data, list):
            analyses, meta = data, {}
        else:
            analyses, meta = data.get("analyses", []), data.get("meta", {})
        total_docs += len(analyses)
        if APPLY:
            up, mod = upsert_analyses(db, analyses, d, meta, os.path.basename(f))
            total_up += up
            total_mod += mod
            print(f"  {os.path.basename(f):32} {len(analyses):>5} 筆 → 新增{up} 更新{mod}")
        else:
            print(f"  {os.path.basename(f):32} {len(analyses):>5} 筆")

    print(f"\n檔案 {len(files)}  文件總數 {total_docs}")
    if APPLY:
        print(f"寫入: 新增 {total_up}  更新 {total_mod}")
        print(f"team_analysis 現有文件: {db['team_analysis'].count_documents({})}")
    else:
        print("[DRY-RUN] 未寫入。加 --apply 執行。")


if __name__ == "__main__":
    main()
