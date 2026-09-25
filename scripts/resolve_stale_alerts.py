#!/usr/bin/env python3
"""排程告警自動消解 —— 防止 schedule_alerts 無限累積(2026-09 曾堆到 661)。

背景:多數告警源沒有 auto-resolve,條件解除後告警永不消;有些還把 info 通知塞進來。
兩個月就堆成一面「紅牆」淹沒真訊號。本 job 每日掃描,把「已過保存期」的未解決告警
自動標為 resolved(仍留庫,可稽核/還原),讓儀表板只剩近期真 active。

策略(以「時間」為單一、可解釋的準則):
  - warning 級:超過 TTL_WARNING 天未再更新 → 視為陳舊(若條件仍在,源會有較新告警)
  - info 級:超過 TTL_INFO 天 → info 通知不該長佔告警佇列(應改寫別的集合)
每源保留「最新一則」不動(代表當前狀態),只消更舊的。

用法:
    python scripts/resolve_stale_alerts.py            # 實際消解
    python scripts/resolve_stale_alerts.py --dry-run  # 只報告
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from pymongo import MongoClient

TTL_WARNING_DAYS = 14
TTL_INFO_DAYS = 2


def main() -> int:
    ap = argparse.ArgumentParser(description="排程告警自動消解")
    ap.add_argument("--ttl-warning-days", type=int, default=TTL_WARNING_DAYS)
    ap.add_argument("--ttl-info-days", type=int, default=TTL_INFO_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                     serverSelectionTimeoutMS=5000).tw_stock_analysis
    C = db.schedule_alerts
    now = datetime.now()
    before = C.count_documents({"resolved": {"$ne": True}})

    # 每源最新一則的 _id(保留不動)
    keep = set()
    for r in C.aggregate([{"$match": {"resolved": {"$ne": True}}},
                          {"$sort": {"ts": -1}},
                          {"$group": {"_id": "$source", "latest": {"$first": "$_id"}}}]):
        keep.add(r["latest"])

    def sweep(level_q, cutoff, reason):
        q = {"resolved": {"$ne": True}, "ts": {"$lt": cutoff},
             "_id": {"$nin": list(keep)}, **level_q}
        if args.dry_run:
            return C.count_documents(q)
        return C.update_many(q, {"$set": {"resolved": True, "resolved_at": now,
                                          "resolved_reason": reason}}).modified_count

    warn_cut = now - timedelta(days=args.ttl_warning_days)
    info_cut = now - timedelta(days=args.ttl_info_days)
    n_info = sweep({"level": "info"}, info_cut,
                   f"auto: info 通知逾 {args.ttl_info_days}d(非告警,自動消解)")
    n_warn = sweep({"level": {"$ne": "info"}}, warn_cut,
                   f"auto: 陳舊告警逾 {args.ttl_warning_days}d 未更新(自動消解)")

    after = before - (0 if args.dry_run else (n_info + n_warn))
    tag = "[dry-run] 將消解" if args.dry_run else "已消解"
    print(f"[{now:%Y-%m-%d %H:%M}] 告警自動消解:{tag} info={n_info} warning={n_warn}"
          f" | 未解決 {before} → {after}(每源最新各保留 1 則)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
