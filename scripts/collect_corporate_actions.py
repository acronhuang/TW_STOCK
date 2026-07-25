#!/usr/bin/env python3
"""收集權威『減資/分割』事件 → corporate_actions 集合(供 adj_close 正確還原)。

來源:
  1. TWSE 上市減資恢復買賣參考價(rwd/zh/reducation/TWTAUU)—— 權威事件日+停止前收盤+恢復參考價。
     還原比例 ratio = 恢復參考價 / 停止前收盤(後復權:事件日之前的價 × ratio 使其連續)。
  2. ETF 受益權單位分割(curated,少數,從實際相鄰日收盤驗證比例)。

corporate_actions 欄位:
  symbol, event_date(datetime, 恢復買賣/除權日), type(減資/分割),
  reason, pre_close, ref_price, ratio, source
去重鍵:(symbol, event_date, type)。冪等 upsert。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import requests
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TWTAUU = "https://www.twse.com.tw/rwd/zh/reducation/TWTAUU"
# TPEX 上櫃減資恢復買賣參考價(只給未來~3天滾動窗,故需每日捕捉)
TPEX_REVIVT = "https://www.tpex.org.tw/www/zh-tw/bulletin/revivt"

# ETF 受益權單位分割/反分割(公開事件,少數;比例從實際相鄰交易日收盤算,避免斷層)
ETF_SPLITS = [
    ("0050", "2025-06-18"),   # 1:4 分割
    ("0052", "2025-11-26"),
    ("00887", "2024-10-14"),
]


def _roc_to_dt(s):
    """114/02/12 → datetime(2025,2,12)。"""
    p = str(s).strip().split("/")
    if len(p) != 3:
        return None
    return datetime(int(p[0]) + 1911, int(p[1]), int(p[2]))


def _f(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def fetch_twse_reduction(session, year):
    r = session.get(TWTAUU, params={
        "startDate": f"{year}0101", "endDate": f"{year}1231", "response": "json"},
        headers={"User-Agent": UA}, timeout=30)
    j = r.json()
    if j.get("stat") != "OK":
        return []
    out = []
    for row in j.get("data", []):
        # fields: 0恢復買賣日期 1代號 2名稱 3停止前收盤 4恢復參考價 ... 9減資原因
        ev = _roc_to_dt(row[0])
        sym = str(row[1]).strip()
        pre = _f(row[3])
        ref = _f(row[4])
        if not (ev and sym and pre and ref and pre > 0):
            continue
        out.append({
            "symbol": sym, "event_date": ev, "type": "減資",
            "reason": str(row[9]).strip() if len(row) > 9 else "",
            "pre_close": pre, "ref_price": ref,
            "ratio": round(ref / pre, 6), "source": "TWSE_TWTAUU",
        })
    return out


def fetch_tpex_reduction(session):
    """TPEX 上櫃減資恢復買賣參考價(滾動窗,需每日跑才不漏)。
    欄位: 0恢復買賣日期 1代號 2名稱 3最後交易日收盤 4減資恢復參考價 ... 9減資原因。
    日期是民國 YYY/MM/DD。ratio = 參考價/停止前收盤(同 TWSE)。"""
    try:
        r = session.get(TPEX_REVIVT, headers={"User-Agent": UA}, timeout=25)
        j = r.json()
    except Exception as e:
        print(f"  TPEX 取得失敗: {e}")
        return []
    out = []
    for t in j.get("tables", []):
        for row in t.get("data", []):
            if len(row) < 10:
                continue
            ev = _roc_to_dt(row[0])
            sym = str(row[1]).strip()
            pre = _f(row[3])
            ref = _f(row[4])
            if not (ev and sym and pre and ref and pre > 0):
                continue
            out.append({
                "symbol": sym, "event_date": ev, "type": "減資",
                "reason": str(row[9]).strip() if len(row) > 9 else "",
                "pre_close": pre, "ref_price": ref,
                "ratio": round(ref / pre, 6), "source": "TPEX_revivt",
            })
    return out


def build_etf_splits(db):
    """從 stock_price 實際相鄰交易日算 ETF 分割比例(指定日期→無斷層歧義)。"""
    from bson.decimal128 import Decimal128

    def g(v):
        return float(v.to_decimal()) if isinstance(v, Decimal128) else (float(v) if v is not None else None)

    out = []
    for sym, ds in ETF_SPLITS:
        ev = datetime.fromisoformat(ds)
        post = db.stock_price.find_one({"symbol": sym, "date": {"$gte": ev}}, sort=[("date", 1)])
        pre = db.stock_price.find_one({"symbol": sym, "date": {"$lt": ev}}, sort=[("date", -1)])
        if not (post and pre):
            continue
        pre_c, post_c = g(pre.get("close")), g(post.get("close"))
        # curated 日期可信;ETF 分割會停牌數日,放寬到 ≤14 天(仍擋長期斷層)
        if not (pre_c and post_c) or (post["date"] - pre["date"]).days > 14:
            continue
        out.append({
            "symbol": sym, "event_date": post["date"], "type": "分割",
            "reason": "ETF受益權單位分割", "pre_close": pre_c, "ref_price": post_c,
            "ratio": round(post_c / pre_c, 6), "source": "curated+price",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--db", default="tw_stock_analysis")
    ap.add_argument("--tpex-only", action="store_true",
                    help="只抓 TPEX 上櫃滾動窗(每日 cron 用,快)")
    args = ap.parse_args()

    db = MongoClient("localhost", 27017)[args.db]
    session = requests.Session()

    events = []
    import time

    # TPEX 上櫃(滾動窗,每日都抓)
    tpex = fetch_tpex_reduction(session)
    events.extend(tpex)
    print(f"  TPEX 上櫃減資(當前窗): {len(tpex)} 筆" + (f" {[(e['symbol'], e['ratio']) for e in tpex]}" if tpex else ""))

    if not args.tpex_only:
        for y in range(args.start_year, args.end_year + 1):
            try:
                evs = fetch_twse_reduction(session, y)
                events.extend(evs)
                print(f"  {y}: 上市減資 {len(evs)} 筆")
            except Exception as e:
                print(f"  {y}: 失敗 {e}")
            time.sleep(1.0)

        etf = build_etf_splits(db)
        events.extend(etf)
        print(f"  ETF 分割 {len(etf)} 筆: {[(e['symbol'], e['ratio']) for e in etf]}")

    now = datetime.now()
    ins = upd = 0
    for e in events:
        e["updated_at"] = now
        res = db.corporate_actions.update_one(
            {"symbol": e["symbol"], "event_date": e["event_date"], "type": e["type"]},
            {"$set": e}, upsert=True)
        if res.upserted_id:
            ins += 1
        elif res.modified_count:
            upd += 1
    db.corporate_actions.create_index([("symbol", 1), ("event_date", 1)])
    print(f"\n✅ corporate_actions: 新增 {ins} / 更新 {upd} / 總 {db.corporate_actions.count_documents({})} 筆")


if __name__ == "__main__":
    main()
