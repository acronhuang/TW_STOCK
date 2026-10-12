#!/usr/bin/env python3
"""新聞與重大訊息 RAG 的查詢集評估：recall@k、MRR、前視洩漏，通過才開放上線（寫入門檻檔）。

在 .166 執行（需要 Ollama bge-m3 與 stockrag.news_docs）。門檻檔給 dashboard 判斷新聞檢索可否啟用：
通過且不超過 14 天才開放；未通過、過期或壞檔一律關閉。
用法：python scripts/stockrag_news_eval.py [--queries tests/rag_eval/news_queries.json tests/rag_eval/news_holdout.json tests/rag_eval/news_queries_otc.json] [--no-gate-file] [-v]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
DEFAULT_QUERIES = [str(ROOT / "tests" / "rag_eval" / name) for name in ("news_queries.json", "news_holdout.json", "news_queries_otc.json")]
GATE_FILE = ROOT / "logs" / "rag_news_gate.json"


def hit_matches(hit, spec) -> bool:
    if "symbol" in spec:
        return hit.get("symbol") == spec["symbol"] and hit["event_date"].strftime("%Y-%m-%d") == spec["date"]
    return re.search(spec["title_regex"], hit.get("content", "")) is not None


def rank_of(hits, spec):
    for rank, hit in enumerate(hits, 1):
        if hit_matches(hit, spec):
            return rank
    return None


def merge_specs(specs):
    """第一個檔案決定 k、門檻、決策時點與掃描截止日；題目與截止案例全部串接。"""
    merged = {**specs[0], "queries": [], "pit_cases": []}
    for spec in specs:
        merged["queries"] += spec["queries"]
        merged["pit_cases"] += spec["pit_cases"]
    return merged


def intraday_cutoffs(day: str, statement_time: str):
    """發言時間前一秒（應看不到）與發言當下（應看得到）。"""
    moment = datetime.strptime(day + statement_time.zfill(6), "%Y-%m-%d%H%M%S")
    return moment - timedelta(seconds=1), moment


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES, help="查詢集檔（可多個，第一個決定 k、門檻與截止設定）")
    ap.add_argument("--no-gate-file", action="store_true", help="只評估，不更新上線門檻檔")
    ap.add_argument("--half-life", type=float, default=None, help="強制套用此半衰期(天)；預設只在題目說「最近」時才衰減。只用於對照實驗")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    from pymongo import MongoClient

    import stockrag_eval as base_eval
    import stockrag_news as news
    import stockrag_search as rag

    rag.embed = lru_cache(maxsize=None)(rag.embed)
    spec = merge_specs([json.loads(Path(p).read_text(encoding="utf-8")) for p in args.queries])
    k = spec["k"]
    docs, mat = news.load()
    if not docs:
        print("news_docs 是空的，請先跑 stockrag_news_ingest.py")
        return 2
    known = {d["stock_id"]: d.get("stock_name") or "" for d in
             MongoClient()["tw_stock_analysis"]["taiwan_stock_info"].find({}, {"stock_id": 1, "stock_name": 1})}
    print(f"語料 {len(docs)} 則；k={k}；決策時點 {spec['decision_as_of']}")
    decision = rag.parse_as_of(spec["decision_as_of"])

    def retrieve(question, as_of):
        symbols = news.extract_symbols(question, known)
        return news.search(question, docs, mat, k=k, symbols=symbols or None, as_of=as_of,
                           half_life=args.half_life), symbols

    group_names = {"e": "entity+date", "n": "entity", "r": "recent", "t": "topical"}
    ranks, by_kind = [], {name: [] for name in group_names.values()}
    for item in spec["queries"]:
        hits, symbols = retrieve(item["q"], decision)
        rank = rank_of(hits, item["expect"])
        ranks.append(rank)
        by_kind[group_names[item["id"][0]]].append(rank)
        if rank is None or args.verbose:
            print(f"  {'未命中' if rank is None else f'rank {rank}'}  [{item['id']}] {item['q']}  (辨識代號 {symbols})")
            if rank is None:
                for h in hits[:3]:
                    print(f"       得到 {h['symbol']} {h['event_date']:%Y-%m-%d} {h['title'][:30]}")
    summary = base_eval.summarize(ranks, k)
    print(f"\n檢索品質：recall@{k}={summary['recall']:.3f}  MRR={summary['mrr']:.3f}  ({summary['queries']} 題，未命中 {summary['misses']})")
    for name, group in by_kind.items():
        part = base_eval.summarize(group, k)
        print(f"  {name:8} recall@{k}={part['recall']:.3f}  MRR={part['mrr']:.3f}  ({part['queries']} 題)")

    leak_count = 0
    for day in spec["pit_sweep_as_of"]:
        cutoff = rag.parse_as_of(day)
        bad = []
        for item in spec["queries"]:
            hits, _ = retrieve(item["q"], cutoff)
            bad += base_eval.leaks(hits, cutoff)
        leak_count += len(bad)
        print(f"前視掃描 as_of={day}：{len(spec['queries'])} 題，洩漏 {len(bad)} 筆")

    absent_violations = control_missing = 0
    for case in spec["pit_cases"]:
        before, at = (rag.parse_as_of(case["as_of"]),) * 2 if "time" not in case else intraday_cutoffs(case["date"], case["time"])
        target = {"symbol": case["symbol"], "date": case["date"]}
        too_early, _ = retrieve(case["q"], before)
        on_time, _ = retrieve(case["q"], at)
        free, _ = retrieve(case["q"], None)
        leaked = rank_of(too_early, target) is not None
        visible = rank_of(on_time, target) is not None if "time" in case else True
        control = rank_of(free, target) is not None
        absent_violations += leaked or not visible
        control_missing += not control
        status = "FAIL 截止前就看到了" if leaked else ("FAIL 發言當下反而看不到" if not visible else ("無鑑別力：對照組找不到" if not control else "ok"))
        print(f"截止案例 [{case['id']}]：{status}")

    failures = base_eval.failed_gates(summary, leak_count, absent_violations, spec["thresholds"], control_missing)
    passed = not failures
    print("\n" + ("全部閘門通過" if passed else "未通過：\n  - " + "\n  - ".join(failures)))
    if not args.no_gate_file:
        news.write_gate(GATE_FILE, summary, passed, k, datetime.now())
        print(f"上線門檻檔已更新：{GATE_FILE}（{'開放' if passed else '關閉'}）")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
