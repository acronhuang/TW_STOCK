#!/usr/bin/env python3
"""台股研究篩選 CLI —— 全市場多因子綜合分 → 🟢🟡🔴 研究候選名單。

重用 StockRanker（value/quality/momentum/safety/institutional/growth 六維加權，
financial_check 已剔除 TTM 虧損/高負債地雷股）。輸出為「研究名單」而非「買進名單」。

可排程（每日產出帶日期的 CSV/JSON）。用法：
    python scripts/screen_research.py                      # 預設前 60 檔，門檻 70/50
    python scripts/screen_research.py --limit 100 --green 72 --red 55
    python scripts/screen_research.py --out-dir results    # 另存 CSV+JSON
    python scripts/screen_research.py --quiet              # 只寫檔不印表（排程用）

排程範例（crontab，收盤後、evening_pipeline 之後）：
    30 20 * * 1-5  cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/screen_research.py --out-dir results --quiet \
      >> logs/cron_research_screen.log 2>&1
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")  # 讓 --line 能讀到 LINE 憑證
except Exception:
    pass

from pymongo import MongoClient  # noqa: E402

from src.analysis.stock_ranker import StockRanker  # noqa: E402

DISCLAIMER = ("研究名單 ≠ 買進名單；型態 ≠ 未來上漲；AI 篩選 ≠ 投資保證。"
              "本清單僅供研究起點，投資決策請自行確認。")


def line_message(rows, dstr, top=12):
    greens = [r for r in rows if r["tier"] == "🟢"]
    head = f"🔬 台股研究名單 {dstr}\n🟢 值得深入研究 {len(greens)} 檔（Top {min(top, len(greens))}）"
    body = "\n".join(
        f"{r['symbol']} {r['name']} {r['score']:.1f}"
        for r in greens[:top] if r["score"] is not None)
    return f"{head}\n{body}\n⚠️ 研究名單≠買進名單，僅供研究"


def factor_date(uri="mongodb://localhost:27017/"):
    doc = MongoClient(uri)["tw_stock_analysis"].stock_factors.find_one(
        {"date": {"$type": "date"}}, {"date": 1}, sort=[("date", -1)])
    return doc["date"] if doc else None


def tier_of(score, green, red):
    if score is None:
        return "🟡"
    if score >= green:
        return "🟢"
    if score < red:
        return "🔴"
    return "🟡"


def build_rows(limit, green, red):
    rows = StockRanker().rank(limit=limit, financial_check=True)
    out = []
    for r in rows:
        sc = r.get("scores", {})
        m = r.get("metrics", {})
        score = r.get("total_score")
        out.append({
            "tier": tier_of(score, green, red),
            "symbol": r["symbol"], "name": r.get("name", ""),
            "score": score, "grade": r.get("grade", ""),
            "value": sc.get("value"), "quality": sc.get("quality"),
            "momentum": sc.get("momentum"), "safety": sc.get("safety"),
            "institutional": sc.get("institutional"), "growth": sc.get("growth"),
            "pe": m.get("pe_ratio"), "dividend_yield": m.get("dividend_yield"),
            "roe": m.get("roe"), "rsi_14": m.get("rsi_14"),
        })
    return out


def write_files(rows, out_dir, dstr):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else []
    csv_path = out_dir / f"research_screen_{dstr}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    json_path = out_dir / f"research_screen_{dstr}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"data_date": dstr, "disclaimer": DISCLAIMER, "rows": rows},
                  f, ensure_ascii=False, indent=2)
    return csv_path, json_path


def print_report(rows, dstr, green, red):
    counts = {t: sum(1 for r in rows if r["tier"] == t) for t in ("🟢", "🟡", "🔴")}
    print(f"\n台股研究候選名單 · 因子資料日 {dstr} · 門檻 🟢≥{green} / 🔴<{red}")
    print(f"🟢 {counts['🟢']}　🟡 {counts['🟡']}　🔴 {counts['🔴']}\n")
    for tier, label in [("🟢", "值得深入研究"), ("🟡", "條件部分符合"), ("🔴", "暫不納入研究")]:
        sub = [r for r in rows if r["tier"] == tier]
        print(f"{tier} {label}（{len(sub)} 檔）")
        for r in sub:
            s = f"{r['score']:.1f}" if r["score"] is not None else "—"
            print(f"  {r['symbol']:<6} {r['name']:<8} 綜合{s:>5} 評級{r['grade']}")
        print()
    print("⚠️ " + DISCLAIMER)


def main():
    ap = argparse.ArgumentParser(description="台股研究篩選 → 🟢🟡🔴 研究名單")
    ap.add_argument("--limit", type=int, default=60, help="取綜合分前 N 檔（預設 60）")
    ap.add_argument("--green", type=float, default=70, help="🟢 門檻：綜合分 ≥（預設 70）")
    ap.add_argument("--red", type=float, default=50, help="🔴 門檻：綜合分 <（預設 50）")
    ap.add_argument("--out-dir", default=None, help="另存 CSV+JSON 的目錄（預設不存檔）")
    ap.add_argument("--quiet", action="store_true", help="只寫檔不印表（需搭配 --out-dir）")
    ap.add_argument("--line", action="store_true", help="推播 🟢 名單摘要到 LINE（遵守 LINE_SPOOL）")
    a = ap.parse_args()

    if a.red > a.green:
        print("⚠️ --red 不應高於 --green", file=sys.stderr)

    dstr = (str(factor_date())[:10]) or datetime.now().strftime("%Y-%m-%d")
    rows = build_rows(a.limit, a.green, a.red)
    if not rows:
        print("無評分結果 —— 可能 stock_factors 無資料或財報篩檢過嚴。", file=sys.stderr)
        sys.exit(1)

    if a.out_dir:
        csv_path, json_path = write_files(rows, a.out_dir, dstr)
        if a.quiet:
            counts = {t: sum(1 for r in rows if r["tier"] == t) for t in ("🟢", "🟡", "🔴")}
            print(f"[{dstr}] 研究名單已寫出：🟢{counts['🟢']} 🟡{counts['🟡']} 🔴{counts['🔴']} "
                  f"→ {csv_path} / {json_path}")

    if a.line:
        from src.alerts.line_notifier import LineNotifier
        ok = LineNotifier().send(line_message(rows, dstr))
        print(f"[LINE] {'已送出/暫存' if ok else '未發送（未設定或停用）'}")

    if not a.quiet:
        print_report(rows, dstr, a.green, a.red)


if __name__ == "__main__":
    main()
