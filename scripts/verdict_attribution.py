#!/usr/bin/env python3
"""AI verdict 事後歸因 —— 命中率 / 校準回饋迴路。

背景：team_analysis 已存 final_verdict + price_at_analysis + date。本腳本撈「約 N 交易日前」
的 verdict，取現價比對，算命中率與分票別校準，寫入 verdict_metrics，供 Dashboard 面板與
「換模型/節點/prompt」的 A/B 客觀依據。

用法（建議每日 cron）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/verdict_attribution.py --horizon-days 20

唯讀主資料（team_analysis / stock_price），只寫 verdict_metrics。
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit.ab_verdict import build_trend_series  # noqa: E402
from src.audit.verdict_tracker import (  # noqa: E402
    build_hitrate_alert,
    compute_metrics,
    evaluate_verdict,
)
from src.config import get_db  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_SCHEDULE_ALERTS,
    COLL_STOCK_PRICE,
    COLL_TEAM_ANALYSIS,
    COLL_VERDICT_METRICS,
)


def _current_close(db, symbol: str):
    doc = db[COLL_STOCK_PRICE].find_one({"symbol": symbol}, {"close": 1},
                                        sort=[("date", -1)])
    if not doc:
        return None
    c = doc.get("close")
    return float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon-days", type=int, default=20,
                    help="評估 N 日曆天前的 verdict（預設 20）")
    ap.add_argument("--tolerance-days", type=int, default=5,
                    help="目標日期前後容忍區間（找最近的分析批次）")
    args = ap.parse_args()

    db = get_db()
    now = datetime.now()
    target = now - timedelta(days=args.horizon_days)
    lo = target - timedelta(days=args.tolerance_days)
    hi = target + timedelta(days=args.tolerance_days)

    records = list(db[COLL_TEAM_ANALYSIS].find(
        {"date": {"$gte": lo, "$lte": hi},
         "final_verdict": {"$exists": True},
         "price_at_analysis": {"$ne": None}},
        {"symbol": 1, "final_verdict": 1, "price_at_analysis": 1, "date": 1}))

    evaluated = []
    for r in records:
        later = _current_close(db, r["symbol"])
        if later is None:
            continue
        ev = evaluate_verdict(r, later)
        if ev:
            evaluated.append(ev)

    metrics = compute_metrics(evaluated)
    metrics_doc = {
        "ts": now, "horizon_days": args.horizon_days,
        "eval_window": {"from": lo, "to": hi},
        "n": metrics["n"], "hit_rate": metrics["hit_rate"],
        "avg_return": metrics["avg_return"], "by_verdict": metrics["by_verdict"],
    }
    try:
        db[COLL_VERDICT_METRICS].insert_one(metrics_doc)
    except Exception as e:
        print(f"⚠️ 寫入 {COLL_VERDICT_METRICS} 失敗：{e}")

    # 命中率趨勢告警（連 N 期下滑 / 跌破地板）→ schedule_alerts（選配 LINE）
    hist = list(db[COLL_VERDICT_METRICS].find(
        {}, {"ts": 1, "hit_rate": 1}).sort("ts", 1).limit(180))
    series = build_trend_series(hist, "hit_rate")
    max_drops = int(os.getenv("VERDICT_HITRATE_ALERT_DROPS", "3"))
    floor_env = os.getenv("VERDICT_HITRATE_ALERT_FLOOR", "")
    floor = float(floor_env) if floor_env else None
    alert = build_hitrate_alert(series, max_consecutive_drops=max_drops, floor=floor)
    if alert:
        try:
            db[COLL_SCHEDULE_ALERTS].insert_one({
                "ts": now, "level": alert["level"], "source": "verdict_attribution",
                "message": alert["message"], "detail": alert["detail"], "resolved": False,
            })
            print(f"🔴 {alert['message']}")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 寫入 {COLL_SCHEDULE_ALERTS} 失敗：{e}")
        if os.getenv("VERDICT_ALERT_LINE") == "1":
            try:
                from src.alerts.line_notifier import LineNotifier
                LineNotifier().send("⚠️ " + alert["message"])
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ LINE 發送失敗：{e}")

    hr = f"{metrics['hit_rate']:.1%}" if metrics["hit_rate"] is not None else "N/A"
    print(f"[{now:%Y-%m-%d}] verdict 歸因（{args.horizon_days}日）：n={metrics['n']} 命中率={hr}")
    for v, b in sorted(metrics["by_verdict"].items()):
        bhr = f"{b['hit_rate']:.1%}" if b.get("hit_rate") is not None else "N/A"
        print(f"  {v}: n={b['n']} 命中率={bhr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
