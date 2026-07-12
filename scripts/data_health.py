#!/usr/bin/env python3
"""
資料健康監控（P2 · 主動）。
不等異常才反應——每日記錄健康快照、比對歷史趨勢，在覆蓋率「緩慢劣化」還沒跨過完整度門檻前就示警；
另可對核心表做 FinMind 外部交叉驗證。

模式:
  data_health.py --snapshot            記錄今日健康快照到 data_health_history
  data_health.py --trend               比對近 7/30 天，覆蓋率明顯下降則示警（→LINE）
  data_health.py --finmind N           對 N 檔抽查，核對 DB 收盤/PE vs FinMind（外部驗證）
  data_health.py --report              印出近 14 天趨勢表（人看）
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import requests
import urllib3
from bson import Decimal128
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")
from dotenv import load_dotenv

load_dotenv("/home/mdsadmin/Stock/tw-stock-analysis/.env")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.getenv("FINMIND_API_TOKEN", "")
TOL = 0.03  # 收盤價相對容差

# 覆蓋率下降超過此百分點（vs 7 天前）即示警
COVERAGE_DROP_WARN = 3.0
_MKT = {"symbol": {"$ne": "TAIEX"}}


def _tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ref_date(db):
    d = db.stock_price.find_one({"date": {"$exists": True}, **_MKT}, {"date": 1}, sort=[("date", -1)])
    return d["date"] if d else None


def snapshot(db) -> dict:
    """計算今日健康快照。coverage = 上市櫃池(taiwan_stock_info) ∩ 有資料 / 池大小。"""
    listed = set(db.taiwan_stock_info.distinct("stock_id"))
    n_listed = len(listed) or 1
    ref = _ref_date(db)

    def cov(symbols):
        return round(len(listed & set(symbols)) / n_listed * 100, 2)

    snap = {
        "date": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
        "listed": len(listed),
        "ref_date": ref,
        "collections": {
            "stock_price": {
                "coverage": cov(db.stock_price.distinct("symbol", _MKT)),
                "latest_count": db.stock_price.count_documents({"date": ref, **_MKT}) if ref else 0,
            },
            "stock_factors": {
                "coverage": cov(db.stock_factors.distinct("symbol")),
                "rsi_coverage": round(
                    db.stock_factors.count_documents({"date": ref, "rsi_14": {"$ne": None}}) / n_listed * 100, 2) if ref else 0,
            },
            "quarterly_earnings": {"coverage": cov(db.quarterly_earnings.distinct("symbol"))},
            "institutional_flow": {"coverage": cov(db.institutional_flow.distinct("stock_id"))},
        },
        "created_at": datetime.now(),
    }
    return snap


def do_snapshot(db):
    snap = snapshot(db)
    db.data_health_history.update_one({"date": snap["date"]}, {"$set": snap}, upsert=True)
    # 心跳：讓 watchdog.py 能偵測「健康快照 job 是否有跑」
    db.system_heartbeat.update_one(
        {"_id": "health"},
        {"$set": {"last_run": datetime.now(), "status": "ok"}}, upsert=True)
    c = snap["collections"]
    print(f"[{snap['date'].date()}] 健康快照已記錄")
    print(f"  股價覆蓋 {c['stock_price']['coverage']}%  因子 {c['stock_factors']['coverage']}%"
          f"  財報 {c['quarterly_earnings']['coverage']}%  法人 {c['institutional_flow']['coverage']}%")


def do_trend(db):
    """比對近 7 天，覆蓋率明顯下降 → 示警。"""
    hist = list(db.data_health_history.find().sort("date", -1).limit(31))
    if len(hist) < 2:
        print("歷史快照不足，無法比對趨勢（先累積幾天）")
        return
    now = hist[0]
    wk = next((h for h in hist if (now["date"] - h["date"]).days >= 7), hist[-1])
    problems = []
    for coll in ("stock_price", "stock_factors", "quarterly_earnings", "institutional_flow"):
        c_now = now["collections"][coll]["coverage"]
        c_wk = wk["collections"][coll]["coverage"]
        drop = c_wk - c_now
        if drop >= COVERAGE_DROP_WARN:
            problems.append(f"{coll} 覆蓋率 {c_wk}%→{c_now}%（{wk['date'].date()} 起 -{drop:.1f}pt）")
    print(f"趨勢比對：今日 {now['date'].date()} vs {wk['date'].date()}")
    if problems:
        print("  ⚠️ 覆蓋率劣化：")
        for p in problems:
            print("   ", p)
        _line("⚠️ 資料覆蓋率緩慢劣化（尚未觸發完整度門檻，但趨勢向下）：\n" + "\n".join(problems))
    else:
        print("  ✅ 覆蓋率穩定，無劣化趨勢")


def _finmind_close(sym, d):
    try:
        ds = d.strftime("%Y-%m-%d")
        r = requests.get(FINMIND_URL, params={"dataset": "TaiwanStockPrice", "data_id": sym,
                         "start_date": ds, "end_date": ds, "token": FINMIND_TOKEN}, timeout=20)
        if r.status_code != 200:
            return None
        rows = [x for x in r.json().get("data", []) if str(x.get("date")) == ds]
        c = _tof(rows[0].get("close")) if rows else None
        return c if c else None
    except Exception:
        return None


def do_finmind(db, n):
    """核心表外部交叉驗證：抽 N 檔，核對 DB 收盤 vs FinMind。"""
    if not FINMIND_TOKEN:
        print("⚠️ 無 FINMIND_API_TOKEN"); return
    ref = _ref_date(db)
    if not ref:
        print("無參考日"); return
    import time
    listed = [s for s in db.taiwan_stock_info.distinct("stock_id") if s.isdigit() and len(s) == 4]
    # 均勻抽樣（不用亂數，取等距）
    step = max(1, len(listed) // n)
    sample = listed[::step][:n]
    match = mism = noresp = 0
    for s in sample:
        d = db.stock_price.find_one({"symbol": s, "date": ref}, {"close": 1})
        db_c = _tof(d["close"]) if d else None
        fm_c = _finmind_close(s, ref)
        if db_c is None or fm_c is None:
            noresp += 1
        elif abs(db_c - fm_c) <= max(TOL, abs(fm_c) * TOL):
            match += 1
        else:
            mism += 1
        time.sleep(0.4)
    total = match + mism
    rate = round(match / total * 100, 1) if total else 0
    print(f"FinMind 交叉驗證 @ {ref.date()}：抽 {len(sample)} 檔  相符 {match}  背離 {mism}  無對照 {noresp}  → 符合率 {rate}%")
    db.data_health_history.update_one({"date": snapshot(db)["date"]},
        {"$set": {"finmind_check": {"sample": len(sample), "match": match, "mism": mism,
                  "rate": rate, "checked_at": datetime.now()}}}, upsert=True)
    if total and rate < 95:
        _line(f"🚨 FinMind 交叉驗證符合率僅 {rate}%（{ref.date()}，抽 {len(sample)} 檔）→ DB 收盤可能與外部源背離")


def do_report(db):
    hist = list(db.data_health_history.find().sort("date", -1).limit(14))
    if not hist:
        print("尚無健康快照"); return
    print("日期        股價%  因子%  財報%  法人%  FinMind%")
    for h in reversed(hist):
        c = h["collections"]
        fm = h.get("finmind_check", {}).get("rate", "-")
        print(f"{h['date'].date()}  {c['stock_price']['coverage']:>5}  {c['stock_factors']['coverage']:>5}"
              f"  {c['quarterly_earnings']['coverage']:>5}  {c['institutional_flow']['coverage']:>5}  {fm:>6}")


def _line(msg):
    try:
        from src.alerts.line_notifier import LineNotifier
        n = LineNotifier()
        if n.enabled:
            n.send(f"📉 {datetime.now():%Y-%m-%d %H:%M} 資料健康\n{msg}")
    except Exception as e:
        print("LINE 發送失敗:", e)


def main():
    ap = argparse.ArgumentParser(description="資料健康監控（主動）")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--trend", action="store_true")
    ap.add_argument("--finmind", type=int, metavar="N")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]
    if args.snapshot:
        do_snapshot(db)
    if args.trend:
        do_trend(db)
    if args.finmind:
        do_finmind(db, args.finmind)
    if args.report:
        do_report(db)
    if not any([args.snapshot, args.trend, args.finmind, args.report]):
        ap.print_help()


if __name__ == "__main__":
    main()
