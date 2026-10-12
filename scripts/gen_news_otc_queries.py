#!/usr/bin/env python3
"""從上櫃、興櫃的真實重大訊息抽樣產生評估題目（一次性工具，不做調校）。

題目形式與既有集相同：「公司簡稱 + 公告主旨」，期望命中該公司該日公告。
抽樣規則：指定亂數種子、每家公司最多一題、排除既有查詢集用過的公司、公司名稱須能在 taiwan_stock_info 解析。

用法：
  python3 scripts/gen_news_otc_queries.py --seed 20261014 --otc 25 --rotc 15 \
      --start 2026-07-14 --end 2026-10-11 --out tests/rag_eval/news_queries_otc.json
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 太短或只剩制式字樣的主旨沒有檢索意義
MIN_SUBJECT_CHARS = 8
SUBJECT_MAX = 40


def short_name(name: str) -> str:
    return re.sub(r"[-*＊\s]+$", "", name or "").replace("股份有限公司", "").strip()


def clean_subject(subject: str, name: str) -> str:
    s = re.sub(r"\s+", " ", subject or "").strip()
    for n in sorted({name, short_name(name)}, key=len, reverse=True):
        if n and s.startswith(n):
            s = s[len(n):].strip()
            break
    s = re.sub(r"^[\s:：,，、]+", "", s)
    return s[:SUBJECT_MAX].strip()


def used_symbols(paths):
    used = set()
    for p in paths:
        fp = Path(p)
        if not fp.exists():
            continue
        spec = json.loads(fp.read_text(encoding="utf-8"))
        for q in spec.get("queries", []):
            sym = (q.get("expect") or {}).get("symbol")
            if sym:
                used.add(str(sym))
    return used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--otc", type=int, default=25)
    ap.add_argument("--rotc", type=int, default=15)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude", nargs="*", default=[
        str(ROOT / "tests" / "rag_eval" / "news_queries.json"),
        str(ROOT / "tests" / "rag_eval" / "news_holdout.json"),
    ])
    args = ap.parse_args()

    from src.config import get_db

    db = get_db()
    names = {str(d["stock_id"]): d.get("stock_name")
             for d in db["taiwan_stock_info"].find({}, {"stock_id": 1, "stock_name": 1})
             if d.get("stock_name")}
    start = datetime.strptime(args.start, "%Y-%m-%d")
    end_excl = datetime.strptime(args.end, "%Y-%m-%d") + timedelta(days=1)
    skip = used_symbols(args.exclude)
    rng = random.Random(args.seed)

    queries = []
    for market, want in (("otc", args.otc), ("rotc", args.rotc)):
        rows = list(db["major_news"].find(
            {"market": market, "date": {"$gte": start, "$lt": end_excl}, "detail": {"$nin": [None, ""]}},
            {"stock_id": 1, "name": 1, "date": 1, "subject": 1}))
        by_stock = {}
        unknown = {str(r["stock_id"]) for r in rows if str(r["stock_id"]) not in names}
        for r in rows:
            sid = str(r["stock_id"])
            if sid in skip or sid not in names:
                continue
            subj = clean_subject(r.get("subject", ""), r.get("name", ""))
            if len(subj) < MIN_SUBJECT_CHARS:
                continue
            by_stock.setdefault(sid, []).append((r["date"].strftime("%Y-%m-%d"), subj, r.get("name", "")))
        ids = sorted(by_stock)
        rng.shuffle(ids)
        for sid in ids[:want]:
            date, subj, name = rng.choice(sorted(by_stock[sid]))
            queries.append({
                "id": f"n-{sid}",
                "q": f"{short_name(name)} {subj}",
                "expect": {"symbol": sid, "date": date},
                "market": market,
            })
        total = len({str(r["stock_id"]) for r in rows})
        print(f"{market}: 區間內有公告的公司 {total}，不在 taiwan_stock_info 而無法出題 {len(unknown)}，"
              f"候選 {len(ids)}，取 {min(want, len(ids))}", file=sys.stderr)

    spec = {
        "version": 1,
        "note": f"上櫃、興櫃新題目：種子 {args.seed}，一次性首次評估，不做調校。",
        "k": 5,
        "decision_as_of": args.end,
        "thresholds": {"recall": 0.8, "mrr": 0.5},
        "pit_sweep_as_of": [],
        "pit_cases": [],
        "queries": queries,
    }
    Path(args.out).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫出 {len(queries)} 題 -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
