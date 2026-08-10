#!/usr/bin/env python3
"""institutional_investors_wide 每日增量:從 institutional_flow 同步尾端。

背景:wide(重建歷史 2005+,ChipAnalyzer 消費)由一次性 rebuild 產生、無 cron → 漂移。
實測 wide.{foreign,trust,dealer,total}_net 與 institutional_flow 完全 1:1 相同
(2023 起重疊每檔每日 ratio=1.0),而 flow 每日由 twse_openapi_sync 免費維護。
故 wide 尾端直接從 flow 同步即可,免 FinMind 配額。

用法: sync_wide_from_flow.py [--days N | --from YYYY-MM-DD]
  預設:補 wide 最新日之後、flow 已有的所有日。
"""
import argparse
from datetime import datetime, timezone, timedelta

from bson.decimal128 import Decimal128
from pymongo import MongoClient, UpdateOne

NET = ["foreign_net", "trust_net", "dealer_net", "total_net"]
# TWSE T86(上市)比 TPEX(上櫃)晚~1天落地;只取「>wide最新日」會讓晚到的 T86 永遠漏。
# 故每次重掃最近 RESYNC_DAYS 天(upsert 冪等,補進晚到的上市法人)。
RESYNC_DAYS = 7


def to_num(v):
    if isinstance(v, Decimal128):
        return int(v.to_decimal())
    if isinstance(v, float):
        return int(v)
    return v


def to_utc_midnight(dt):
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="回溯 N 天(0=自動接 wide 最新日)")
    ap.add_argument("--from", dest="frm", default="")
    args = ap.parse_args()
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]
    wide = db.institutional_investors_wide
    flow = db.institutional_flow

    if args.frm:
        since = datetime.strptime(args.frm, "%Y-%m-%d")
    elif args.days:
        since = datetime.now() - timedelta(days=args.days)
    else:
        latest = wide.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
        base = latest["date"] if latest else datetime(2023, 1, 1)
        since = base - timedelta(days=RESYNC_DAYS)
    # 滾動窗口:取 flow 中 date >= since 的資料重掃(upsert 冪等,補晚到的 T86 上市法人)
    q = {"date": {"$gte": since}}
    docs = list(flow.find(q))
    print(f"從 institutional_flow 取 date >= {str(since)[:10]} 共 {len(docs):,} 筆")
    if not docs:
        print("wide 已是最新,無需同步"); return

    ops = []
    for d in docs:
        sid = d.get("stock_id")
        fd = d.get("date")
        if not sid or not fd:
            continue
        doc = {"stock_id": sid, "date": to_utc_midnight(fd),
               "source": "institutional_flow_sync", "updated_at": datetime.now(timezone.utc)}
        for k in NET:
            if d.get(k) is not None:
                doc[k] = to_num(d[k])
        ops.append(UpdateOne({"stock_id": sid, "date": doc["date"]}, {"$set": doc}, upsert=True))
    res = wide.bulk_write(ops, ordered=False)
    days = sorted(set(str(to_utc_midnight(d["date"]))[:10] for d in docs if d.get("date")))
    print(f"upsert {len(ops):,} (新增 {res.upserted_count}, 更新 {res.modified_count})")
    print(f"涵蓋 {len(days)} 日: {days}")
    newlatest = wide.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
    print(f"wide 最新日 → {str(newlatest['date'])[:10]}")


if __name__ == "__main__":
    main()
