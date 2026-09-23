#!/usr/bin/env python3
"""verdict A/B 評估 —— 比三臂超額報酬 + 量化 Ollama vs 規則 的差異。

對 verdict_ab 中「已到期（約 N 日前記錄）」的三臂決策，取現價算各臂超額報酬與命中率，
並比對 Ollama 臂 vs 規則臂的一致率/分歧矩陣、以及分歧時「誰對」。

用法（唯讀，不寫入）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/verdict_ab_eval.py --horizon-days 20
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit.ab_verdict import build_agreement_alert, compare_verdict_sets  # noqa: E402
from src.audit.verdict_tracker import forward_return, is_hit, normalize_verdict  # noqa: E402
from src.config import get_db  # noqa: E402
from src.monitoring.data_quality import auto_resolve_alerts  # noqa: E402
from src.domain.collections import (  # noqa: E402
    COLL_SCHEDULE_ALERTS,
    COLL_STOCK_PRICE,
    COLL_VERDICT_AB,
    COLL_VERDICT_AB_METRICS,
)

BAND = 0.03


def _f(c):
    return float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)


def _close_latest(db, sym):
    d = db[COLL_STOCK_PRICE].find_one({"symbol": sym}, {"close": 1}, sort=[("date", -1)])
    return _f(d.get("close")) if d else None


def _arm_stats(pairs, market_avg):
    """pairs: [(verdict, ret)]。回 n/avg_excess/hit(相對)。"""
    rows = [(v, r) for v, r in pairs if r is not None and v]
    n = len(rows)
    if n == 0:
        return dict(n=0, exc_avg=None, hit=None)
    exc = [r - market_avg for _, r in rows]
    hits = sum(1 for (v, r) in rows if is_hit(normalize_verdict(v), r - market_avg))
    return dict(n=n, exc_avg=sum(exc) / n, hit=hits / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon-days", type=int, default=20)
    ap.add_argument("--tolerance-days", type=int, default=6)
    ap.add_argument("--persist", action="store_true",
                    help="將一致率/三臂統計寫入 verdict_ab_metrics，供趨勢追蹤。")
    args = ap.parse_args()

    db = get_db()
    now = datetime.now()
    target = now - timedelta(days=args.horizon_days)
    lo, hi = target - timedelta(days=args.tolerance_days), target + timedelta(days=args.tolerance_days)

    recs = list(db[COLL_VERDICT_AB].find({"recorded_at": {"$gte": lo, "$lte": hi}}))
    if not recs:
        print(f"verdict_ab 在 {lo:%m-%d}~{hi:%m-%d} 無到期記錄；請先跑 verdict_ab_record.py 並等 {args.horizon_days} 天。")
        return

    # 市場母體基準
    universe = [d["_id"] for d in db[COLL_STOCK_PRICE].aggregate(
        [{"$group": {"_id": "$symbol"}}, {"$limit": 600}])]
    mret = []
    for s in universe:
        cur = _close_latest(db, s)
        past = db[COLL_STOCK_PRICE].find_one({"symbol": s, "date": {"$lte": hi}},
                                             {"close": 1}, sort=[("date", -1)])
        pc = _f(past.get("close")) if past else None
        r = forward_return(pc, cur) if (cur and pc) else None
        if r is not None:
            mret.append(r)
    market_avg = sum(mret) / len(mret) if mret else 0.0

    arms = {"base": [], "rule_gate": [], "ollama": []}
    ollama_map, rule_map = {}, {}
    for r in recs:
        later = _close_latest(db, r["symbol"])
        ret = forward_return(_f(r.get("entry_price")), later) if later else None
        a = r.get("arms", {})
        for arm in arms:
            arms[arm].append((a.get(arm), ret))
        if a.get("ollama"):
            ollama_map[r["symbol"]] = a["ollama"]
        if a.get("rule_gate"):
            rule_map[r["symbol"]] = a["rule_gate"]

    print(f"verdict A/B 評估 @ {now:%Y-%m-%d}（持有期 {args.horizon_days}日，n={len(recs)}，市場均報酬 {market_avg:+.2%}）")
    print(f"{'臂':<10} {'n':>4} {'超額均值':>9} {'相對命中':>8}")
    print("-" * 40)
    for arm in ("base", "rule_gate", "ollama"):
        s = _arm_stats(arms[arm], market_avg)
        if s["n"]:
            print(f"{arm:<10} {s['n']:>4} {s['exc_avg']:>+8.2%} {s['hit']:>7.1%}")
        else:
            print(f"{arm:<10} {0:>4} {'—':>9} {'—':>8}")

    # Ollama vs 規則 差異
    cmp = compare_verdict_sets(rule_map, ollama_map)
    print("-" * 40)
    print(f"Ollama vs 規則：一致率 {cmp['agreement_rate']:.1%}（n={cmp['n']}，分歧 {len(cmp['changed'])} 檔）"
          if cmp["agreement_rate"] is not None else "Ollama vs 規則：無共同標的")
    if cmp["matrix"]:
        print("  分歧矩陣 (規則→Ollama)：")
        for (b, v), c in sorted(cmp["matrix"].items()):
            if b != v:
                print(f"    規則 {b} → Ollama {v}: {c}")

    if args.persist:
        arm_stats = {arm: _arm_stats(arms[arm], market_avg) for arm in arms}
        doc = {
            "ts": now,
            "horizon_days": args.horizon_days,
            "n": len(recs),
            "market_avg": market_avg,
            "agreement_rate": cmp["agreement_rate"],
            "agreement_n": cmp["n"],
            "changed_count": len(cmp["changed"]),
            "arms": {
                arm: {"n": s["n"], "exc_avg": s["exc_avg"], "hit": s["hit"]}
                for arm, s in arm_stats.items()
            },
        }
        try:
            db[COLL_VERDICT_AB_METRICS].insert_one(doc)
            print(f"✅ 已寫入 {COLL_VERDICT_AB_METRICS}（趨勢追蹤）")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 寫入 {COLL_VERDICT_AB_METRICS} 失敗：{e}")

        # 一致率跨門檻→寫排程警報（網頁可見），選配 LINE
        threshold = float(os.getenv("VERDICT_AGREEMENT_ALERT_THRESHOLD", "0.6"))
        alert = build_agreement_alert(
            cmp["agreement_rate"], threshold, n=cmp["n"], changed_count=len(cmp["changed"]))
        if alert:
            try:
                db[COLL_SCHEDULE_ALERTS].insert_one({
                    "ts": now, "level": alert["level"], "source": "verdict_ab_eval",
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
        elif cmp["agreement_rate"] is not None:
            try:
                n_res = auto_resolve_alerts(db, "verdict_ab_eval", now=now)
                if n_res:
                    print(f"✅ 一致率回穩，自動消警 {n_res} 筆")
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ 自動消警失敗：{e}")


if __name__ == "__main__":
    main()
