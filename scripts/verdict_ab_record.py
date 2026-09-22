#!/usr/bin/env python3
"""verdict A/B 前瞻記錄 —— 平行記錄三臂決策供日後比超額。

三臂：① base(現行Ollama合議)  ② rule_gate(規則動能閘門)  ③ ollama(Ollama帶動能重判)。
對每個標的算 MA20/MA60 → 趨勢，產生三臂 verdict，寫入 verdict_ab（含 entry_price/date）。
日後由 verdict_ab_eval.py 比三臂超額報酬，並量化 Ollama vs 規則 的差異。

用法（在 .166 執行，Ollama 臂需連 .28）:
    cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/verdict_ab_record.py --limit 60
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audit.ab_verdict import apply_momentum_gate, ollama_momentum_verdict, trend_signal  # noqa: E402
from src.config import get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE, COLL_TEAM_ANALYSIS, COLL_VERDICT_AB  # noqa: E402


def _f(c):
    return float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)


def _ma(db, sym, n):
    rows = list(db[COLL_STOCK_PRICE].find({"symbol": sym}, {"close": 1})
                .sort([("date", -1)]).limit(n))
    closes = [_f(r.get("close")) for r in rows if _f(r.get("close"))]
    return sum(closes) / len(closes) if len(closes) >= n else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="處理標的數上限（Ollama 呼叫成本）")
    ap.add_argument("--date", type=str, default=None, help="team_analysis 日期 YYYY-MM-DD，預設最新")
    args = ap.parse_args()

    db = get_db()
    from src.moe.role_router import ask_role  # 延遲載入（Ollama 臂）

    q = {"final_verdict": {"$exists": True}, "price_at_analysis": {"$ne": None}}
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d")
        q["date"] = {"$gte": d, "$lt": d.replace(hour=23, minute=59)}
    recs = list(db[COLL_TEAM_ANALYSIS].find(q, {"symbol": 1, "final_verdict": 1,
                "price_at_analysis": 1, "date": 1}).sort([("date", -1)]).limit(args.limit))

    now = datetime.now()
    written = 0
    for r in recs:
        sym = r["symbol"]
        price = _f(r.get("price_at_analysis"))
        ma20, ma60 = _ma(db, sym, 20), _ma(db, sym, 60)
        trend = trend_signal(price, ma20, ma60)
        base = r["final_verdict"]
        rule = apply_momentum_gate(base, trend)
        ollama = ollama_momentum_verdict(sym, base,
                                         {"price": price, "ma20": ma20, "ma60": ma60}, ask_role)
        doc = {
            "symbol": sym, "date": r.get("date", now), "recorded_at": now,
            "entry_price": price, "trend": trend,
            "indicators": {"price": price, "ma20": ma20, "ma60": ma60},
            "arms": {"base": base, "rule_gate": rule, "ollama": ollama},
        }
        try:
            db[COLL_VERDICT_AB].update_one(
                {"symbol": sym, "date": doc["date"]},
                {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
            written += 1
        except Exception as e:
            print(f"⚠️ {sym} 寫入失敗：{e}")

    print(f"[{now:%Y-%m-%d %H:%M}] verdict A/B 記錄 {written} 檔（Ollama 臂含 None={sum(1 for r in recs if True)}）")
    print("　三臂已存 verdict_ab，待 N 日後 verdict_ab_eval.py 評估。")


if __name__ == "__main__":
    main()
