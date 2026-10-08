#!/usr/bin/env python3
"""
新聞價值回測 —— 用數據回答「餵新聞的 verdict 命中率是否 > 不餵」。
================================================================
解鎖條件：team_analysis 需有結構化 news_count/catalyst 欄位
（src/moe/team_store.py 自 2026-10 起寫入；部署後新跑的合議才有）。

做法：把每筆團隊合議（date, symbol, final_verdict, catalyst）對上後續 N 日
前瞻報酬（adj_close，與 research_hitrate 同口徑），依「有無新聞佐證」分組，
比較買進類 verdict 的平均報酬與勝率。若 catalyst 這一刀切不出差異，
代表新聞對 verdict 沒有增量貢獻——這正是當初接新聞時缺的驗證。

用法:
  news_value_backtest.py --horizon 20                抽所有有 catalyst 欄位的歷史回測
  news_value_backtest.py --horizon 10 --entry open   隔日開盤進場
  news_value_backtest.py --min-samples 30            樣本不足就只報「資料累積中」
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient  # noqa: E402

BUY_VERDICTS = ("強力買進", "買進")


def _db():
    return MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGODB_DATABASE", "tw_stock_analysis")
    ]


def _g(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def _fwd_return(db, symbol, date, horizon, entry_mode):
    """單檔前瞻報酬%（adj_close 口徑）。資料不足回 None。"""
    need = horizon + 2
    px = list(db.stock_price.find(
        {"symbol": symbol, "date": {"$gte": date}},
        {"adj_close": 1, "close": 1, "adj_open": 1, "open": 1}).sort("date", 1).limit(need))
    try:
        if entry_mode == "close":
            if len(px) <= horizon:
                return None
            p0 = _g(px[0].get("adj_close")) or _g(px[0].get("close"))
            pn = _g(px[horizon].get("adj_close")) or _g(px[horizon].get("close"))
        else:  # 隔日開盤
            if len(px) <= horizon + 1:
                return None
            p0 = _g(px[1].get("adj_open")) or _g(px[1].get("open"))
            pn = _g(px[horizon + 1].get("adj_close")) or _g(px[horizon + 1].get("close"))
        if not p0 or not pn:
            return None
        return (pn / p0 - 1) * 100
    except (IndexError, TypeError, ZeroDivisionError):
        return None


def _stats(rets):
    if not rets:
        return {"n": 0, "avg": None, "win": None}
    return {
        "n": len(rets),
        "avg": round(sum(rets) / len(rets), 2),
        "win": round(100 * sum(1 for r in rets if r > 0) / len(rets), 1),
    }


def main():
    ap = argparse.ArgumentParser(description="新聞價值回測（catalyst 分組命中率）")
    ap.add_argument("--horizon", type=int, default=20, help="前瞻交易日數（預設 20）")
    ap.add_argument("--entry", choices=["close", "open"], default="close",
                    help="進場：當日收盤 / 隔日開盤")
    ap.add_argument("--min-samples", type=int, default=20,
                    help="每組最少樣本數，不足則提示資料累積中")
    args = ap.parse_args()
    db = _db()

    # 只取有 catalyst 欄位、且為買進類 verdict 的歷史（買進最能驗證新聞的增量價值）
    q = {"catalyst": {"$exists": True}, "final_verdict": {"$in": list(BUY_VERDICTS)}}
    docs = list(db.team_analysis.find(
        q, {"symbol": 1, "date": 1, "final_verdict": 1, "catalyst": 1, "news_count": 1}))
    total = db.team_analysis.count_documents({"catalyst": {"$exists": True}})
    print(f"team_analysis 有 catalyst 欄位的文件：{total} 筆；其中買進類：{len(docs)} 筆")

    if total == 0:
        print("⏳ 尚無 catalyst 結構化欄位——部署後新跑的團隊合議才會寫入。先累積數日再回測。")
        return

    with_news, without_news = [], []
    for d in docs:
        sym, dt = d.get("symbol"), d.get("date")
        if not sym or not dt:
            continue
        r = _fwd_return(db, sym, dt, args.horizon, args.entry)
        if r is None:
            continue
        (with_news if d.get("catalyst") else without_news).append(r)

    sa, sb = _stats(with_news), _stats(without_news)
    print(f"\n進場={args.entry}  前瞻={args.horizon}日  （買進類 verdict）")
    print(f"  🟢 有新聞佐證(catalyst=True) ：n={sa['n']:>3}  平均報酬 {sa['avg']}%  勝率 {sa['win']}%")
    print(f"  ⚪ 無新聞佐證(catalyst=False)：n={sb['n']:>3}  平均報酬 {sb['avg']}%  勝率 {sb['win']}%")

    if sa["n"] < args.min_samples or sb["n"] < args.min_samples:
        print(f"\n⏳ 樣本不足（需每組 ≥{args.min_samples}），結論暫不可靠——持續累積中。")
        return

    edge_avg = round((sa["avg"] or 0) - (sb["avg"] or 0), 2)
    edge_win = round((sa["win"] or 0) - (sb["win"] or 0), 1)
    print(f"\n  新聞增量：平均報酬 {edge_avg:+}pp，勝率 {edge_win:+}pp")
    if edge_avg > 0.5 and edge_win > 0:
        print("  ✅ 有新聞佐證的買進表現較佳——新聞對 verdict 有正向增量價值。")
    elif edge_avg < -0.5:
        print("  ⚠️ 有新聞佐證的買進反而較差——需檢視是否追高利多/同名雜訊干擾。")
    else:
        print("  ≈ 兩組差異不顯著——新聞目前對 verdict 無明顯增量，值得檢討餵法。")

    # 落地一份快照供趨勢追蹤
    db.news_value_backtest.update_one(
        {"horizon": args.horizon, "entry": args.entry},
        {"$set": {"horizon": args.horizon, "entry": args.entry,
                  "with_news": sa, "without_news": sb,
                  "edge_avg_pp": edge_avg, "edge_win_pp": edge_win,
                  "updated_at": datetime.now()}}, upsert=True)


if __name__ == "__main__":
    main()
