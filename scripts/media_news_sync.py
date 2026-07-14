#!/usr/bin/env python3
"""
media_news_sync —— 全市場媒體新聞「預抓快取」
================================================
把全市場 ~2000 檔的 Google News 標題先抓進 media_news 表，供團隊分析（尤其週五
全市場 ~2000 檔那場）從 DB 讀，而非分析當下逐檔即時外抓（2000 次連續請求會被
Google 限流／擋 IP，反而全抓不到）。與即時抓相比：涵蓋率最高、對 Google 有禮貌
（一週一輪＋節流）、和 14 小時分析解耦、抓失敗不影響分析。

設計：
  - 節流：每檔間隔 --sleep 秒（預設 0.8）；連續失敗自動退避，降被擋機率。
  - 冪等：今天已抓過的（fetched_at 為今日）預設略過；中斷可續跑；--force 全重抓。
  - fail-open：單檔抓不到就存空 titles（仍記 fetched_at＝已查過），不影響其他檔。
  - 清單與 team_daily_verified.select_universe_all 一致：有價 4 碼個股，去 ETF/受益/存託。

排程：週五 19:30（全市場團隊分析 21:00 前），crontab  30 19 * * 5
用法：
  python scripts/media_news_sync.py                # 全市場（~2000 檔，約 30~50 分）
  python scripts/media_news_sync.py --limit 30     # 測試前 30 檔
  python scripts/media_news_sync.py --force        # 忽略今日已抓、全部重抓
"""
import argparse
import os
import re
import sys
import time
from datetime import datetime

from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.analysis.news_evidence import google_titles   # 共用抓取＋regex 解析（避 XXE）

DB = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))["tw_stock_analysis"]


def universe() -> list[tuple[str, str]]:
    """與 team_daily_verified.select_universe_all 一致：有價 4 碼個股，去 ETF/受益/存託。"""
    syms = set(s for s in DB.stock_price.distinct("symbol") if re.fullmatch(r"\d{4}", str(s)))
    info = {d["stock_id"]: d for d in DB.taiwan_stock_info.find(
        {}, {"stock_id": 1, "industry_category": 1, "stock_name": 1})}
    EXCL = ("ETF", "指數股票型", "受益", "存託")
    out = []
    for sym in sorted(syms):
        ti = info.get(sym)
        ind = (ti or {}).get("industry_category")
        if not ti or not ind or any(w in ind for w in EXCL):
            continue
        out.append((sym, ti.get("stock_name")))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="只抓前 N 檔（測試）")
    ap.add_argument("--sleep", type=float, default=0.8, help="每檔間隔秒（禮貌性節流）")
    ap.add_argument("--force", action="store_true", help="忽略今日已抓，全部重抓")
    args = ap.parse_args()

    DB.media_news.create_index("code", unique=True)
    DB.media_news.create_index("fetched_at")

    targets = universe()
    if args.limit:
        targets = targets[:args.limit]
    total = len(targets)
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"[{datetime.now():%F %T}] media_news 預抓開始：{total} 檔，sleep={args.sleep}s，force={args.force}",
          flush=True)
    got = skip = empty = 0
    fails = 0     # 連續失敗計數 → 退避
    for i, (code, name) in enumerate(targets, 1):
        if not args.force:
            ex = DB.media_news.find_one({"code": code}, {"fetched_at": 1})
            if ex and ex.get("fetched_at") and ex["fetched_at"].strftime("%Y-%m-%d") == today:
                skip += 1
                continue
        titles = google_titles(name)      # 純標題（無前綴）；抓不到回 []
        DB.media_news.update_one(
            {"code": code},
            {"$set": {"code": code, "name": name, "titles": titles,
                      "fetched_at": datetime.now()}},
            upsert=True)
        if titles:
            got += 1
            fails = 0
        else:
            empty += 1
            fails += 1
        # 連續多檔空 → 可能被限流，加長退避
        extra = 3.0 if fails and fails % 8 == 0 else 0.0
        if i % 200 == 0 or i == total:
            print(f"  {i}/{total}  有新聞 {got} / 空 {empty} / 略過 {skip}", flush=True)
        time.sleep(args.sleep + extra)

    print(f"[{datetime.now():%F %T}] 完成：有新聞 {got}、空 {empty}、略過(今日已抓) {skip}", flush=True)


if __name__ == "__main__":
    main()
