#!/usr/bin/env python3
"""核心池每日追蹤:刷新 core_watchlist 快照 + 掃每檔今日進出場訊號,有觸發才寫 schedule_alerts(網頁查,不發LINE)。

進場訊號(核心股當日出現較佳時機):2560做量/縮量、量價型態低位放量·跟上/量增價升·買入、跌深反彈潛力高。
出場/警示:量價型態高位放量·跑路/量增價跌·減倉。
核心池=品質 ∩ 委員買進 ∩ 外資背書(src.analysis.core_pool)。跑完寫網頁「🔔排程警報」source=core_watchlist。

用法: core_watchlist_daily.py   (每日收盤後 cron)
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient

from src.analysis.core_pool import build_core_pool
from src.analysis.strategy_2560 import classify_2560
from src.analysis.volprice_pattern import classify_tf
from src.analysis.tech_lines import price_series, rebound_potential

ENTRY = ("低位放量·跟上", "量增價升·果斷買入")
EXIT = ("高位放量·跑路", "量增價跌·及時減倉", "量平價跌·堅決出局")


def _signals(db, sym):
    df = price_series(db, sym, 170)
    if df.empty or len(df) < 65 or "volume" not in df:
        return [], []
    cl = df["close"].tolist(); vo = df["volume"].tolist()
    s2560 = classify_2560(cl, vo)
    vp = classify_tf(cl, vo, "月")
    rp = rebound_potential(db, sym)
    entry, warn = [], []
    if s2560 and s2560["setup"] and s2560["scenario"] in ("做量", "縮量"):
        entry.append(f"2560{s2560['scenario']}")
    if vp and any(x in vp["label"] for x in ENTRY):
        entry.append(vp["label"].split("·")[0])
    if rp and rp["verdict"] == "反彈潛力高":
        entry.append("反彈潛力高")
    if vp and any(x in vp["label"] for x in EXIT):
        warn.append("月線" + vp["label"].split("·")[0])
    return entry, warn


def main():
    now = datetime.now()
    db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))["tw_stock_analysis"]
    meta, core = build_core_pool(db)
    if core.empty:
        print("核心池為空,略過"); return

    # 快照落地(供追溯/頁面)
    db.core_watchlist.update_one(
        {"_id": "current"},
        {"$set": {"updated_at": now, "meta": meta,
                  "stocks": core[["代號", "名稱", "綜合分", "外資10日淨買(張)"]].to_dict("records")}},
        upsert=True)

    entries, warns = [], []
    for _, r in core.iterrows():
        e, w = _signals(db, r["代號"])
        tag = f"{r['代號']}{r['名稱']}"
        if e:
            entries.append(f"{tag}:{'/'.join(e)}")
        if w:
            warns.append(f"{tag}:{'/'.join(w)}")
    print(f"核心池 {meta['n_core']} 檔(合議 {meta['buy_date']});進場訊號 {len(entries)} · 警示 {len(warns)}")

    lines = []
    if entries:
        lines.append("🟢 進場時機(" + str(len(entries)) + "檔):")
        lines += ["  " + x for x in entries[:25]]
    if warns:
        lines.append("🔴 警示(" + str(len(warns)) + "檔):")
        lines += ["  " + x for x in warns[:15]]
    if lines:
        msg = f"🏆 核心池{meta['n_core']}檔今日訊號" + chr(10) + chr(10).join(lines)
        try:
            db.schedule_alerts.create_index([("ts", -1)])
            db.schedule_alerts.insert_one({"ts": now, "level": "info", "source": "core_watchlist",
                                           "message": msg, "resolved": False})
            print("已寫 schedule_alerts(網頁🔔排程警報可查)")
        except Exception as e:
            print("寫入失敗:", repr(e))
    else:
        print("今日核心池無進場/警示訊號(靜默)")


if __name__ == "__main__":
    main()
