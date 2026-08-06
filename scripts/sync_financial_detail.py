#!/usr/bin/env python3
"""財報明細三表同步 → balance_sheet_detail / cash_flows_detail / financial_statement_detail。

背景:現金流量表 TWSE/TPEX OpenAPI 完全沒有(143 端點無此表),只能走 FinMind。
既然現金流量非 FinMind 不可,三表就都用 FinMind — 一支下載器、一種 long 格式、上市櫃統一、11 年史。

來源(FinMind,實測免費 token 可抓、上市+上櫃、2015 起):
  綜合損益表 TaiwanStockFinancialStatements → financial_statement_detail
  資產負債表 TaiwanStockBalanceSheet        → balance_sheet_detail
  現金流量表 TaiwanStockCashFlowsStatement   → cash_flows_detail

格式(FinMind 原生 long/tidy):{stock_id, date, type, value, origin_name}
  → 寫入時 date 轉 datetime、加 updated_at;upsert key = (stock_id, date, type)。

配額:免費層 per-stock 查詢(不准無 data_id 整日)、600 calls/hr。每檔 3 dataset = 3 calls。
  → --limit 控每次檔數(預設 190 檔 ≈ 570 calls < 600/hr);碰 402 優雅停、存 state、下次續跑。
  財報季頻,首次全回填分批/過夜跑一輪,之後每季財報截止後增量(只補缺季、已到位的檔 0 call)。

用法:
  # 首次全回填(2015 起,可重複跑續傳,每次 190 檔)
  sync_financial_detail.py --full --limit 190
  # 增量(每季 cron;只補缺最新季的檔)
  sync_financial_detail.py
  # 單檔測試
  sync_financial_detail.py --sym 2330 --full
"""
import argparse
import os
import time
import logging
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
load_dotenv(os.path.join(ROOT, ".env"))
TOKEN = os.getenv("FINMIND_API_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
API = "https://api.finmindtrade.com/api/v4/data"

# dataset → 目標 collection(綜合損益/資產負債/現金流量)
DATASETS = {
    "financial_statement_detail": "TaiwanStockFinancialStatements",
    "balance_sheet_detail":       "TaiwanStockBalanceSheet",
    "cash_flows_detail":          "TaiwanStockCashFlowsStatement",
}
STATE_COL = "financial_detail_backfill_state"  # {stock_id, done_full, updated_at}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


class QuotaExhausted(Exception):
    """FinMind 402:配額用盡。"""


def expected_latest_quarter(today=None):
    """依台股財報申報截止日,回傳『今天應已公布的最新季底 datetime』。
    Q1(3/31)→5/15、Q2(6/30)→8/14、Q3(9/30)→11/14、Q4(12/31)→隔年3/31。"""
    today = today or datetime.now()
    y = today.year
    deadlines = [
        (datetime(y, 3, 31),  datetime(y - 1, 12, 31)),   # 去年 Q4,3/31 前
        (datetime(y, 5, 15),  datetime(y, 3, 31)),        # Q1,5/15 前
        (datetime(y, 8, 14),  datetime(y, 6, 30)),        # Q2,8/14 前
        (datetime(y, 11, 14), datetime(y, 9, 30)),        # Q3,11/14 前
        (datetime(y + 1, 3, 31), datetime(y, 12, 31)),    # 今年 Q4
    ]
    latest = datetime(y - 1, 9, 30)
    for deadline, qend in deadlines:
        if today >= deadline:
            latest = qend
    return latest


def fetch(dataset, sid, start):
    """抓單檔單 dataset。402→QuotaExhausted;其他錯→回 None(視為暫時失敗)。"""
    try:
        r = requests.get(API, params={"dataset": dataset, "data_id": sid,
                                      "start_date": start, "token": TOKEN}, timeout=40)
    except requests.RequestException as e:
        log.warning(f"  {sid}/{dataset}: 連線錯 {e!r}")
        return None
    if r.status_code == 402:
        raise QuotaExhausted()
    if r.status_code != 200:
        log.warning(f"  {sid}/{dataset}: HTTP {r.status_code}")
        return None
    return r.json().get("data", [])


def upsert_rows(col, sid, rows):
    """long 格式 rows → upsert by (stock_id, date, type)。回 (寫入筆數, 最新季底 str)。"""
    ops = []
    latest = ""
    for rec in rows:
        d = rec.get("date")
        typ = rec.get("type")
        if not d or not typ:
            continue
        dt = datetime.strptime(d[:10], "%Y-%m-%d")
        ops.append(UpdateOne(
            {"stock_id": sid, "date": dt, "type": typ},
            {"$set": {"stock_id": sid, "date": dt, "type": typ,
                      "value": rec.get("value"), "origin_name": rec.get("origin_name"),
                      "updated_at": datetime.now()}},
            upsert=True))
        latest = max(latest, d[:10])
    if ops:
        col.bulk_write(ops, ordered=False)
    return len(ops), latest


def load_universe(db, syms=None):
    """上市+上櫃、普通股/KY股、4 位數代號。回 [stock_id,...] 排序。"""
    if syms:
        return syms
    q = {"type": {"$in": ["twse", "tpex"]},
         "security_type": {"$in": ["Stock", "KY-Stock"]},
         "stock_id": {"$regex": "^[0-9]{4}$"}}
    return sorted(db.taiwan_stock_info.distinct("stock_id", q))


def main():
    ap = argparse.ArgumentParser(description="財報明細三表 FinMind 同步")
    ap.add_argument("--full", action="store_true", help="全回填模式(2015起,resume via state);否則增量只補缺最新季")
    ap.add_argument("--start", default="2015-01-01", help="全回填起始日(預設 2015-01-01)")
    ap.add_argument("--limit", type=int, default=560, help="本次最多 API calls(<600/hr;每檔3 calls;跳過的檔不計)")
    ap.add_argument("--delay", type=float, default=0.35, help="每次 API call 間隔秒(限流)")
    ap.add_argument("--sym", help="只處理指定代號(逗號分隔)")
    ap.add_argument("--datasets", help="只處理指定表(逗號分隔 collection 名)")
    ap.add_argument("--dry-run", action="store_true", help="只印不寫")
    args = ap.parse_args()

    if not TOKEN:
        raise SystemExit("❌ 未設定 FINMIND_API_TOKEN")

    db = MongoClient(MONGO_URI)["tw_stock_analysis"]
    for coll in DATASETS:
        db[coll].create_index([("stock_id", 1), ("date", -1), ("type", 1)], unique=True)
    state = db[STATE_COL]

    targets = list(DATASETS.items())
    if args.datasets:
        want = set(args.datasets.split(","))
        targets = [(c, d) for c, d in targets if c in want]

    syms = [s.strip() for s in args.sym.split(",")] if args.sym else None
    universe = load_universe(db, syms)
    exp_latest = expected_latest_quarter()
    log.info(f"股票池 {len(universe)} 檔 | 模式={'全回填' if args.full else '增量'} | "
             f"應有最新季底={exp_latest:%Y-%m-%d} | limit={args.limit}")

    if args.full and not syms:
        done = set(state.distinct("stock_id", {"done_full": True}))
        universe = [s for s in universe if s not in done]
        log.info(f"  已完成全回填 {len(done)} 檔,剩 {len(universe)} 檔待處理")

    processed = calls = written = skipped = 0
    quota_hit = False
    for sid in universe:
        if calls >= args.limit:  # 以 API call 為上限(整檔原子:在檔起點才 break)
            log.info(f"達本次 API call 上限 {args.limit}(已處理 {processed} 檔),其餘下次續跑")
            break
        sid_written = 0
        try:
            for coll, dataset in targets:
                col = db[coll]
                if args.full:
                    start = args.start
                else:
                    mx = col.find_one({"stock_id": sid}, sort=[("date", -1)])
                    if mx and mx["date"] >= exp_latest:
                        skipped += 1
                        continue  # 已到位,免 call
                    start = ((mx["date"] + timedelta(days=1)).strftime("%Y-%m-%d")
                             if mx else args.start)
                rows = fetch(dataset, sid, start)
                calls += 1
                if args.delay:
                    time.sleep(args.delay)
                if not rows:
                    continue
                if args.dry_run:
                    log.info(f"  [dry] {sid}/{coll}: {len(rows)} 筆(start={start})")
                    continue
                n, latest = upsert_rows(col, sid, rows)
                sid_written += n
        except QuotaExhausted:
            log.warning(f"⛔ FinMind 402 配額用盡(已處理 {processed} 檔)。已存進度,下次同指令續跑。")
            quota_hit = True
            break
        written += sid_written
        processed += 1
        if args.full and not args.dry_run and sid not in (syms or []):
            state.update_one({"stock_id": sid},
                             {"$set": {"done_full": True, "updated_at": datetime.now()}},
                             upsert=True)
        if processed % 25 == 0:
            log.info(f"  進度 {processed}/{min(args.limit, len(universe))} | calls={calls} 寫入={written:,} 跳過={skipped}")

    log.info("=" * 60)
    log.info(f"完成:處理 {processed} 檔 | API calls {calls} | 寫入 {written:,} 筆 | 跳過(已到位) {skipped}")
    if not args.full:
        for coll in [c for c, _ in targets]:
            mx = db[coll].find_one(sort=[("date", -1)])
            log.info(f"  {coll}: 總 {db[coll].estimated_document_count():,} 筆,最新 {str(mx['date'])[:10] if mx else '無'}")
    if quota_hit:
        raise SystemExit(0)  # 配額停不算錯,cron 不噴紅


if __name__ == "__main__":
    main()
