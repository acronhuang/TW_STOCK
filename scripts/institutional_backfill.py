#!/usr/bin/env python3
"""
三大法人買賣超歷史回補（TWSE T86 + TPEX，一次性）
==================================================
為什麼需要：institutional_flow 僅 2026-02-24 起（約 5 個月）。這使得
  (1) 任何「法人訊號」的回測都只有 ~20 個週期 → 結論是雜訊；
  (2) 無法檢定新因子（如大戶集中度）在既有法人訊號**之上**是否有增量價值。
shareholding 已回補到 2023-03（norway），法人補齊後兩者期間才對得上。

來源（皆支援指定日期，實測 2023–2026 全可用）：
  上市 TWSE T86  https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&selectType=ALLBUT0999
       直接重用 twse_daily_update.fetch_twse_institutional(date_str)，欄位對應一致。
  上櫃 TPEX      https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php
       ?l=zh-tw&se=EW&t=D&d=民國/MM/DD
       註：twse_daily_update 用的 OpenAPI(tpex_3insti_daily_trading) **只給當日**，
       無法回補；其 docstring 提到的失效端點是 tpex_buysell_sec_date，與本端點不同 ——
       本端點 2026-07-17 實測 112/113/114/115 年皆正常回傳。

TPEX 欄位（fields 只重複寫「買進/賣出/買賣超」不含分組名，故以位置對應，
並用算術不變量驗證，避免欄位錯位默默寫入壞資料）：
   [ 4] 外資及陸資(不含外資自營商)   [ 7] 外資自營商
   [10] 外資及陸資合計 = [4]+[7]     [13] 投信
   [16] 自營商(自行買賣)             [19] 自營商(避險)
   [22] 自營商合計 = [16]+[19]       [23] 三大法人合計 = [10]+[13]+[22]
  → 寫入 foreign_net=[10], trust_net=[13], dealer_net=[22], total_net=[23]，
    與 twse_daily_update 的 OpenAPI 對應（外資及陸資合計/投信/自營商合計/TotalDifference）一致。

用法：
    python3 scripts/institutional_backfill.py --dry-run --limit 3
    python3 scripts/institutional_backfill.py                    # 補到 shareholding 起點
    python3 scripts/institutional_backfill.py --start 2024-01-01
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from pymongo import ASCENDING, MongoClient, UpdateOne

sys.path.insert(0, str(Path(__file__).parent))
from twse_daily_update import _to_dec, fetch_twse_institutional   # noqa: E402

TPEX_URL = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

# 位置對應（見模組 docstring）
C_FOREIGN, C_TRUST, C_DEALER, C_TOTAL = 10, 13, 22, 23

SLEEP = 1.5        # 每個來源請求間隔（證交所/櫃買為公務網站，禮貌性節流）
RETRIES = 3


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _roc(d) -> str:
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _get(url, **kw):
    last = None
    for i in range(RETRIES):
        try:
            r = requests.get(url, timeout=45, headers=UA, **kw)
            r.raise_for_status()
            return r
        except Exception as e:      # noqa: BLE001
            last = e
            if i < RETRIES - 1:
                time.sleep(3 * (2 ** i))
    raise RuntimeError(f"抓取失敗（{RETRIES} 次）：{last}")


def fetch_tpex_dated(d) -> list[dict]:
    """上櫃三大法人（指定日）。非交易日回空清單。"""
    r = _get(TPEX_URL, params={"l": "zh-tw", "se": "EW", "t": "D", "d": _roc(d)})
    try:
        j = r.json()
    except ValueError:
        return []
    tables = j.get("tables") or []
    if not tables:
        return []
    rows = tables[0].get("data") or []
    out, bad = [], 0
    for row in rows:
        if len(row) <= C_TOTAL:
            continue
        sid = str(row[0]).strip()
        if not sid.isdigit():          # 僅普通股，與 twse_daily_update 一致（排除 00679B 等）
            continue
        f, t, dl, tot = (_num(row[C_FOREIGN]), _num(row[C_TRUST]),
                         _num(row[C_DEALER]), _num(row[C_TOTAL]))
        if None in (f, t, dl, tot):
            continue
        # 不變量：外資+投信+自營 = 合計。不符 → 欄位錯位，寧可整日不寫也不寫壞資料
        if abs((f + t + dl) - tot) > 1:
            bad += 1
            continue
        out.append({
            "stock_id": sid, "date": datetime(d.year, d.month, d.day),
            "foreign_net": _to_dec(str(f)), "trust_net": _to_dec(str(t)),
            "dealer_net": _to_dec(str(dl)), "total_net": _to_dec(str(tot)),
            "data_source": "TPEX_3INSTI", "updated_at": datetime.now(),
        })
    if bad and bad > len(out) * 0.01:
        raise RuntimeError(f"TPEX {d} 有 {bad} 列不符『外資+投信+自營=合計』→ 疑似欄位改版，中止")
    return out


def trading_days(db, start, end) -> list:
    """交易日曆取自 stock_price（排除 macro_sync 塞入的 TAIEX）。"""
    ds = db.stock_price.distinct("date", {
        "date": {"$gte": datetime.combine(start, datetime.min.time()),
                 "$lte": datetime.combine(end, datetime.min.time())},
        "symbol": {"$ne": "TAIEX"}})
    return sorted({d.date() if isinstance(d, datetime) else d for d in ds if d})


def main():
    ap = argparse.ArgumentParser(description="三大法人歷史回補")
    ap.add_argument("--start", help="起日 YYYY-MM-DD（預設：shareholding 最早資料日）")
    ap.add_argument("--end", help="迄日 YYYY-MM-DD（預設：institutional_flow 最早日的前一天）")
    ap.add_argument("--limit", type=int, help="只跑前 N 個交易日（試跑用）")
    ap.add_argument("--sleep", type=float, default=SLEEP)
    ap.add_argument("--no-tpex", action="store_true", help="只補上市")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)[os.getenv("MONGODB_DATABASE", "tw_stock_analysis")]
    col = db.institutional_flow

    # 預設補「shareholding 起點 ~ institutional_flow 現有最早日」這段空缺
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        d0 = col.find_one({}, sort=[("date", 1)])
        sh = db.shareholding.find_one({}, sort=[("date", 1)])
        start = (sh["date"].date() if sh else datetime(2023, 3, 1).date())
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        d0 = col.find_one({}, sort=[("date", 1)])
        end = (d0["date"].date() - timedelta(days=1)) if d0 else datetime.now().date()

    days = trading_days(db, start, end)
    if args.limit:
        days = days[:args.limit]
    if not days:
        print("無需回補（區間內無交易日）")
        return

    print(f"回補三大法人｜{start} ~ {end}｜{len(days)} 個交易日"
          f"｜預估 {len(days) * args.sleep * (1 if args.no_tpex else 2) / 60:.0f} 分鐘")
    if not args.dry_run:
        col.create_index([("stock_id", ASCENDING), ("date", ASCENDING)], unique=True)

    ins = failed = 0
    for n, d in enumerate(days, 1):
        recs = []
        for label, fn in (("TWSE", lambda: fetch_twse_institutional(d.strftime("%Y-%m-%d"))),
                          ("TPEX", lambda: fetch_tpex_dated(d))):
            if label == "TPEX" and args.no_tpex:
                continue
            try:
                recs += fn()
            except Exception as e:      # noqa: BLE001 - 單日單來源失敗不中斷整批
                print(f"  ⚠️ {d} {label} 失敗：{str(e)[:90]}")
                failed += 1
            time.sleep(args.sleep)

        if not recs:
            continue
        if args.dry_run:
            tw = sum(1 for r in recs if r["data_source"] == "TWSE_T86")
            print(f"  {d}: {len(recs)} 筆（上市 {tw} / 上櫃 {len(recs) - tw}）"
                  f" 例 {recs[0]['stock_id']} total={recs[0]['total_net']}")
            continue
        # $setOnInsert：不覆蓋既有（每日 pipeline 寫的）資料，只填空缺
        ops = [UpdateOne({"stock_id": r["stock_id"], "date": r["date"]},
                         {"$setOnInsert": r}, upsert=True) for r in recs]
        res = col.bulk_write(ops, ordered=False)
        ins += res.upserted_count
        if n % 20 == 0 or n == len(days):
            print(f"  [{n}/{len(days)}] {d} 累計新增 {ins:,} 筆")

    print(f"✅ 完成：{'DRY-RUN 未寫入' if args.dry_run else f'新增 {ins:,} 筆'}｜失敗 {failed} 次")


if __name__ == "__main__":
    main()
