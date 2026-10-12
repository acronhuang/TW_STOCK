#!/usr/bin/env python3
"""RAG 查詢集評估：檢索品質（recall@k、MRR）與前視防護。需要 Ollama(bge-m3) 與 stockrag 語料，在 .166 執行。

用法：python scripts/stockrag_eval.py [--queries tests/rag_eval/queries.json] [--no-decay] [-v]
任一閘門未過就以非零結束：前視洩漏必須為 0；recall/MRR 不得低於查詢集內的門檻。
"""
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DEFAULT_QUERIES = HERE.parent / "tests" / "rag_eval" / "queries.json"


def first_rank(expected, hit_paths):
    for rank, path in enumerate(hit_paths, 1):
        if path in expected:
            return rank
    return None


def summarize(ranks, k):
    if not ranks:
        return {"recall": 0.0, "mrr": 0.0, "queries": 0, "misses": 0}
    found = [r for r in ranks if r is not None and r <= k]
    return {"recall": len(found) / len(ranks), "mrr": sum(1 / r for r in ranks if r is not None and r <= k) / len(ranks),
            "queries": len(ranks), "misses": len(ranks) - len(found)}


def leaks(hits, as_of):
    from datetime import datetime
    return [h["path"] for h in hits if not isinstance(h.get("doc_date"), datetime) or h["doc_date"] > as_of]


def failed_gates(summary, leak_count, absent_violations, thresholds, control_missing=0):
    failures = []
    for name in ("recall", "mrr"):
        if summary[name] < thresholds[name]:
            failures.append(f"{name} {summary[name]:.3f} 低於門檻 {thresholds[name]}")
    if leak_count:
        failures.append(f"前視洩漏 {leak_count} 筆（截止日之後或無日期的文件被檢出，必須為 0）")
    if absent_violations:
        failures.append(f"{absent_violations} 個案例中應被截止的文件仍出現")
    if control_missing:
        failures.append(f"{control_missing} 個案例的對照組（不設截止）找不到該文件，案例無鑑別力")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", default=str(DEFAULT_QUERIES))
    ap.add_argument("--no-decay", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    import stockrag_search as rag

    rag.embed = lru_cache(maxsize=None)(rag.embed)   # 同一句查詢在各截止日重複使用
    spec = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    k, half_life = spec["k"], (10**9 if args.no_decay else rag.HALF_LIFE)
    docs, mat = rag.load()
    if not docs:
        print("語料庫是空的")
        return 2
    print(f"語料 {len(docs)} 塊；k={k}；半衰期={'關閉' if args.no_decay else half_life}")

    ranks = []
    for item in spec["queries"]:
        hits = rag.search(item["q"], docs, mat, k=k, half_life=half_life)
        rank = first_rank(item["expect"], [h["path"] for h in hits])
        ranks.append(rank)
        if rank is None or args.verbose:
            print(f"  {'未命中' if rank is None else f'rank {rank}'}  [{item['id']}] {item['q']}")
            if rank is None:
                for h in hits[:3]:
                    print(f"       得到 {h['path']}#{h['chunk_idx']}")
    summary = summarize(ranks, k)
    print(f"\n檢索品質：recall@{k}={summary['recall']:.3f}  MRR={summary['mrr']:.3f}  ({summary['queries']} 題，未命中 {summary['misses']})")

    leak_count = 0
    for day in spec["pit_sweep_as_of"]:
        cutoff = rag.parse_as_of(day)
        bad = []
        for item in spec["queries"]:
            bad += leaks(rag.search(item["q"], docs, mat, k=k, half_life=half_life, as_of=cutoff), cutoff)
        leak_count += len(bad)
        print(f"前視掃描 as_of={day}：{len(spec['queries'])} 題，洩漏 {len(bad)} 筆" + (f" {sorted(set(bad))[:3]}" if bad else ""))

    absent_violations = control_missing = 0
    for case in spec["pit_cases"]:
        cutoff = rag.parse_as_of(case["as_of"])
        cut_paths = {h["path"] for h in rag.search(case["q"], docs, mat, k=10, half_life=half_life, as_of=cutoff)}
        free_paths = {h["path"] for h in rag.search(case["q"], docs, mat, k=10, half_life=half_life)}
        present = [p for p in case["absent"] if p in cut_paths]
        missing_control = [p for p in case["absent"] if p not in free_paths]
        absent_violations += bool(present)
        control_missing += bool(missing_control)
        status = "FAIL 出現了不該出現的文件" if present else ("無鑑別力：對照組找不到" if missing_control else "ok")
        print(f"截止案例 [{case['id']}] as_of={case['as_of']}：{status}")

    failures = failed_gates(summary, leak_count, absent_violations, spec["thresholds"], control_missing)
    print("\n" + ("全部閘門通過" if not failures else "未通過：\n  - " + "\n  - ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
