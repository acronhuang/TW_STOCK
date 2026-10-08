#!/usr/bin/env python3
"""
新聞抓取健康度監控（P2 · 主動）。
========================================================
背景：團隊合議（team_daily_verified / team_analyze）在推播前會即時抓 Google News RSS
餵給分析角色，但 `news_evidence.google_titles()` 是 **fail-open**（逾時/被擋即回空、
分析照跑、不報錯、不留日誌）。好處是穩健，壞處是「新聞源悄悄壞掉」無人察覺——
verdict 會默默失去消息面佐證。本腳本把這個靜默風險變成「可觀測」：

  每日抽樣 N 檔即時打 Google News，統計：
    - success_rate  成功（有回標題）比率
    - empty_rate    空回（連得上但 0 筆）比率
    - fail_rate     連不上/逾時/HTTP 錯比率
    - p50/p95 延遲
  並檢查 media_news 預抓快取新鮮度與 major_news（官方重大訊息）量。
  快照寫入 news_health_history；--alert 時若健康度跌破門檻 → LINE。
  完成寫 system_heartbeat（_id=news_health）供 watchdog 偵測 job 死活。

模式:
  news_health_check.py --snapshot [--sample N]   抽樣實測 + 記錄快照（預設 N=12）
  news_health_check.py --snapshot --alert        同上，健康度不佳則示警（→LINE）
  news_health_check.py --report                  印近 14 天趨勢表（人看）
  news_health_check.py --trend                   比對近 7 天，成功率明顯下滑則示警

門檻（可用環境變數覆寫）：
  NEWS_HEALTH_MIN_SUCCESS   成功率低於此值即告警（預設 0.6 = 60%）
  NEWS_HEALTH_MAX_EMPTY     空回率高於此值即告警（預設 0.5 = 50%）
  NEWS_HEALTH_CACHE_DAYS    快取新鮮度門檻天數（預設 8，與 media_news_for 一致）
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from statistics import median

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from dotenv import load_dotenv  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from src.analysis.news_evidence import google_titles  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_MAJOR_NEWS,
    COLL_MEDIA_NEWS,
    COLL_TAIWAN_STOCK_INFO,
)

load_dotenv(os.path.join(_ROOT, ".env"))

MIN_SUCCESS = float(os.getenv("NEWS_HEALTH_MIN_SUCCESS", "0.6"))
MAX_EMPTY = float(os.getenv("NEWS_HEALTH_MAX_EMPTY", "0.5"))
CACHE_DAYS = int(os.getenv("NEWS_HEALTH_CACHE_DAYS", "8"))
SUCCESS_DROP_WARN = 0.25  # 成功率 vs 7 天前掉超過此值（絕對）→ 趨勢示警


def _get_db():
    return MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGODB_DATABASE", "tw_stock_analysis")
    ]


def _sample_symbols(db, n: int) -> list[tuple[str, str]]:
    """均勻（等距）抽 N 檔四碼上市櫃，附股名。不用亂數→每日可比。"""
    docs = list(
        db[COLL_TAIWAN_STOCK_INFO].find(
            {}, {"stock_id": 1, "stock_name": 1}
        )
    )
    pool = [
        (d["stock_id"], d.get("stock_name") or "")
        for d in docs
        if str(d.get("stock_id", "")).isdigit() and len(str(d["stock_id"])) == 4
    ]
    pool.sort(key=lambda x: x[0])
    if not pool:
        return []
    step = max(1, len(pool) // n)
    return pool[::step][:n]


def _probe(db, n: int) -> dict:
    """抽樣即時打 Google News，統計成功/空回/失敗與延遲。"""
    sample = _sample_symbols(db, n)
    ok = empty = fail = 0
    lats: list[float] = []
    worst_empty: list[str] = []
    for code, name in sample:
        if not name:
            fail += 1
            continue
        t = time.time()
        try:
            titles = google_titles(name)  # fail-open：內部吃掉例外回 []
            dt = time.time() - t
            lats.append(dt)
            # google_titles 回 [] 既可能是「空回」也可能是「失敗被吃掉」。
            # 用延遲粗分：極短（<0.15s，通常是連不上/DNS/逾時立即失敗）判 fail，
            # 否則判 empty（連得上但該檔確實 0 筆）。有標題一律 ok。
            if titles:
                ok += 1
            elif dt < 0.15:
                fail += 1
            else:
                empty += 1
                if len(worst_empty) < 5:
                    worst_empty.append(f"{code}{name}")
        except Exception:
            fail += 1
    total = len(sample) or 1
    return {
        "sample": len(sample),
        "ok": ok,
        "empty": empty,
        "fail": fail,
        "success_rate": round(ok / total, 3),
        "empty_rate": round(empty / total, 3),
        "fail_rate": round(fail / total, 3),
        "lat_p50": round(median(lats), 2) if lats else None,
        "lat_p95": round(sorted(lats)[int(len(lats) * 0.95)], 2) if len(lats) >= 2 else None,
        "empty_samples": worst_empty,
    }


def _cache_health(db) -> dict:
    """media_news 預抓快取新鮮度 + major_news 近 14 日量。"""
    now = datetime.now()
    tot = db[COLL_MEDIA_NEWS].count_documents({})
    fresh = db[COLL_MEDIA_NEWS].count_documents(
        {"fetched_at": {"$gte": now - timedelta(days=CACHE_DAYS)}}
    )
    newest = db[COLL_MEDIA_NEWS].find_one(sort=[("fetched_at", -1)])
    nt = newest.get("fetched_at") if newest else None
    cache_age_days = round((now - nt).total_seconds() / 86400, 1) if nt else None
    major14 = db[COLL_MAJOR_NEWS].count_documents(
        {"date": {"$gte": now - timedelta(days=14)}}
    )
    return {
        "media_total": tot,
        "media_fresh": fresh,
        "media_fresh_rate": round(fresh / tot, 3) if tot else 0,
        "cache_age_days": cache_age_days,
        "major_news_14d": major14,
    }


def _problems(probe: dict, cache: dict) -> list[str]:
    out = []
    if probe["sample"] and probe["success_rate"] < MIN_SUCCESS:
        out.append(
            f"Google News 成功率 {probe['success_rate']*100:.0f}% "
            f"< 門檻 {MIN_SUCCESS*100:.0f}%（抽 {probe['sample']} 檔，"
            f"ok {probe['ok']}/空 {probe['empty']}/失敗 {probe['fail']}）"
        )
    if probe["sample"] and probe["empty_rate"] > MAX_EMPTY:
        out.append(
            f"Google News 空回率 {probe['empty_rate']*100:.0f}% "
            f"> 門檻 {MAX_EMPTY*100:.0f}%（可能被限流或查詢被擋）"
        )
    if cache["cache_age_days"] is not None and cache["cache_age_days"] > CACHE_DAYS:
        out.append(
            f"media_news 預抓快取最新已 {cache['cache_age_days']} 天 "
            f"> {CACHE_DAYS} 天（週五預抓可能漏跑，全市場批次將失去新聞佐證）"
        )
    return out


def _line(msg: str):
    try:
        from src.alerts.line_notifier import LineNotifier

        n = LineNotifier()
        if n.enabled:
            n.send(f"📰 {datetime.now():%Y-%m-%d %H:%M} 新聞抓取健康\n{msg}")
    except Exception as e:
        print("LINE 發送失敗:", e)


def do_snapshot(db, n: int, alert: bool):
    probe = _probe(db, n)
    cache = _cache_health(db)
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    snap = {
        "date": day,
        "probe": probe,
        "cache": cache,
        "created_at": datetime.now(),
    }
    db.news_health_history.update_one({"date": day}, {"$set": snap}, upsert=True)
    db.system_heartbeat.update_one(
        {"_id": "news_health"},
        {"$set": {"last_run": datetime.now(), "status": "ok"}},
        upsert=True,
    )

    print(f"[{day.date()}] 新聞抓取健康快照已記錄")
    print(
        f"  Google News：抽 {probe['sample']} 檔  成功 {probe['ok']}"
        f"（{probe['success_rate']*100:.0f}%） 空回 {probe['empty']}"
        f"（{probe['empty_rate']*100:.0f}%） 失敗 {probe['fail']}"
        f"（{probe['fail_rate']*100:.0f}%）  延遲 p50={probe['lat_p50']}s p95={probe['lat_p95']}s"
    )
    print(
        f"  快取：media_news {cache['media_fresh']}/{cache['media_total']} 新鮮"
        f"（{cache['media_fresh_rate']*100:.0f}%，最新 {cache['cache_age_days']} 天前）"
        f"  官方重大訊息(14d) {cache['major_news_14d']} 筆"
    )
    if probe["empty_samples"]:
        print(f"  空回樣本：{', '.join(probe['empty_samples'])}")

    problems = _problems(probe, cache)
    if problems:
        print("  ⚠️ 健康度異常：")
        for p in problems:
            print("   ", p)
        if alert:
            _line("⚠️ 新聞抓取健康度異常：\n" + "\n".join(f"・{p}" for p in problems))
    else:
        print("  ✅ 新聞抓取健康，無異常")


def do_trend(db):
    hist = list(db.news_health_history.find().sort("date", -1).limit(31))
    if len(hist) < 2:
        print("歷史快照不足，無法比對趨勢（先累積幾天）")
        return
    now = hist[0]
    wk = next((h for h in hist if (now["date"] - h["date"]).days >= 7), hist[-1])
    s_now = now["probe"]["success_rate"]
    s_wk = wk["probe"]["success_rate"]
    drop = s_wk - s_now
    print(f"趨勢比對：今日 {now['date'].date()} vs {wk['date'].date()}")
    print(f"  Google 成功率 {s_wk*100:.0f}% → {s_now*100:.0f}%（{-drop*100:+.0f}pt）")
    if drop >= SUCCESS_DROP_WARN:
        _line(
            f"⚠️ Google News 成功率緩慢劣化：{s_wk*100:.0f}%（{wk['date'].date()}）"
            f"→ {s_now*100:.0f}%（今日），跌 {drop*100:.0f}pt"
        )
    else:
        print("  ✅ 成功率穩定，無劣化趨勢")


def do_report(db):
    hist = list(db.news_health_history.find().sort("date", -1).limit(14))
    if not hist:
        print("尚無新聞健康快照")
        return
    print("日期        成功%  空回%  失敗%  p95(s)  快取新鮮%  官方14d")
    for h in reversed(hist):
        p = h["probe"]
        c = h["cache"]
        print(
            f"{h['date'].date()}  {p['success_rate']*100:>5.0f}  {p['empty_rate']*100:>5.0f}"
            f"  {p['fail_rate']*100:>5.0f}  {str(p.get('lat_p95','-')):>6}"
            f"  {c['media_fresh_rate']*100:>8.0f}  {c['major_news_14d']:>6}"
        )


def main():
    ap = argparse.ArgumentParser(description="新聞抓取健康度監控（主動）")
    ap.add_argument("--snapshot", action="store_true", help="抽樣實測 + 記錄快照")
    ap.add_argument("--sample", type=int, default=12, help="抽樣檔數（預設 12）")
    ap.add_argument("--alert", action="store_true", help="健康度不佳時發 LINE")
    ap.add_argument("--trend", action="store_true", help="比對近 7 天成功率")
    ap.add_argument("--report", action="store_true", help="印近 14 天趨勢表")
    args = ap.parse_args()

    db = _get_db()
    if args.snapshot:
        do_snapshot(db, args.sample, args.alert)
    if args.trend:
        do_trend(db)
    if args.report:
        do_report(db)
    if not any([args.snapshot, args.trend, args.report]):
        ap.print_help()


if __name__ == "__main__":
    main()
