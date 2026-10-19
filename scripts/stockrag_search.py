#!/usr/bin/env python3
"""股票分析 RAG — 檢索(向量 + 字面 兩路 RRF,加時間衰減)

時間衰減是這套設計的重點:專案內 124 份根目錄報告彼此矛盾,不少結論已被推翻 ——
例如 2026-02 的驗證報告說「adj_close 覆蓋率 100% ✅」,但 2026-07-20 已證實那是假的。
不做時間加權,問「adj_close 正常嗎」就會拿到舊報告的錯誤答案。

    score = RRF(向量排名, 字面排名) × 0.5^(文件年齡 / 半衰期)

衰減只作用在「快照類」文件（根目錄報告、results、docs/archive、docs/reports）：它們的結論會被後來的實測推翻。
維護中的文件（ADR、指南、資料字典…）不會因為舊就變錯，不衰減，否則一份正確的舊文件會被一堆較新的文件壓到後面。

繁中沒有分詞,MongoDB 文字索引與 PostgreSQL to_tsvector 都切不出詞,
故「字面」這一路用字元 n-gram 重疊率,不是全文檢索。
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from functools import lru_cache

import numpy as np
from pymongo import MongoClient

import os as _os

sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from src.moe import model_nodes  # noqa: E402

OLLAMA = model_nodes.embed_url()
MODEL = model_nodes.EMBED_MODEL
RRF_K = 60
HALF_LIFE = 180        # 天
SNAPSHOT_DOC_PREFIXES = ("docs/archive/", "docs/reports/", "docs/chat_history.md")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def embed(text):
    req = urllib.request.Request(
        f"{OLLAMA}/api/embeddings",
        data=json.dumps({"model": MODEL, "prompt": text, "options": {"num_ctx": 8192}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["embedding"]


def load(mongo_uri="mongodb://localhost:27017/"):
    """把整個語料載進記憶體。約 3,800 塊 × 1024 維 ≈ 15MB。"""
    col = MongoClient(mongo_uri)["stockrag"].docs
    docs = list(col.find({}, {"embedding": 1, "content": 1, "path": 1, "chunk_idx": 1,
                              "title": 1, "kind": 1, "doc_date": 1}))
    if not docs:
        return None, None
    mat = np.array([d["embedding"] for d in docs], dtype=np.float32)
    mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)   # 正規化 → 內積即 cosine
    for d in docs:
        d.pop("embedding", None)
    return docs, mat


def _grams(s, n=2):
    s = re.sub(r"\s+", "", s.lower())
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def literal_scores(query, docs):
    """字元 bigram 重疊率 —— 繁中無分詞,用這個取代全文檢索。"""
    q = _grams(query)
    if not q:
        return np.zeros(len(docs), dtype=np.float32)
    return np.array([len(q & _grams(d["content"])) / len(q) for d in docs],
                    dtype=np.float32)


def parse_as_of(text):
    """'2026-09-20' = 當天收盤後（含當天產出的文件）；'2026-09-20 08:30' = 精確時點。解析不了就報錯，不可默默關掉防護。"""
    for fmt, end_of_day in (("%Y-%m-%d", True), ("%Y-%m-%d %H:%M", False), ("%Y-%m-%d %H:%M:%S", False)):
        try:
            parsed = datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999) if end_of_day else parsed
    raise ValueError(f"無法解析的 as_of: {text!r}（格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM）")


def decays_with_age(d):
    """快照類（根目錄報告、results、archive、reports）會隨時間被推翻，需衰減；其餘 docs/ 文件是維護中的，不衰減。"""
    return d.get("kind") != "doc" or d.get("path", "").startswith(SNAPSHOT_DOC_PREFIXES)


def search(query, docs, mat, k=5, kind=None, half_life=HALF_LIFE, pool=60, as_of=None, as_of_exempt_kinds=()):
    """as_of：知識截止時點。doc_date 晚於它的文件、以及沒有可驗證日期的文件一律排除（失敗即拒絕），
    文件年齡也改從 as_of 起算。doc_date 是檔案修改時間，紀錄的是「最晚什麼時候內容已存在」，對截止比較是保守上界。
    as_of_exempt_kinds：這些種類不受截止限制（例如仍在維護的技術文件，修改時間晚不代表內容是「未來資訊」）。"""
    qv = np.array(embed(query), dtype=np.float32)
    qv /= (np.linalg.norm(qv) + 1e-9)

    mask = np.ones(len(docs), dtype=bool)
    if kind:
        mask = np.array([d.get("kind") == kind for d in docs])
    if as_of is not None:
        exempt = set(as_of_exempt_kinds)
        mask &= np.array([d.get("kind") in exempt or (isinstance(d.get("doc_date"), datetime) and d["doc_date"] <= as_of)
                          for d in docs])
    idx_all = np.where(mask)[0]
    if idx_all.size == 0:
        return []

    vec = mat[idx_all] @ qv                       # cosine
    lit = literal_scores(query, [docs[i] for i in idx_all])

    top_v = idx_all[np.argsort(-vec)[:pool]]
    top_l = idx_all[np.argsort(-lit)[:pool]]

    rank_v = {gi: r + 1 for r, gi in enumerate(top_v)}
    rank_l = {gi: r + 1 for r, gi in enumerate(top_l)}

    now = as_of if as_of is not None else datetime.now()
    fused = []
    for gi in set(rank_v) | set(rank_l):
        rrf = (1.0 / (RRF_K + rank_v[gi]) if gi in rank_v else 0.0) + \
              (1.0 / (RRF_K + rank_l[gi]) if gi in rank_l else 0.0)
        d = docs[gi]
        dd = d.get("doc_date")
        age = max((now - dd).days, 0) if isinstance(dd, datetime) else 0
        decay = 0.5 ** (age / float(half_life)) if half_life < 10**8 and decays_with_age(d) else 1.0
        fused.append({**d, "rrf": rrf, "age_days": age,
                      "vec_sim": float(vec[np.where(idx_all == gi)[0][0]]),
                      "score": rrf * decay})
    fused.sort(key=lambda x: -x["score"])
    return fused[:k]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--kind", choices=["report", "doc", "result"])
    ap.add_argument("--half-life", type=int, default=HALF_LIFE)
    ap.add_argument("--no-decay", action="store_true", help="關閉時間加權(對照用)")
    ap.add_argument("--as-of", help="知識截止時點 YYYY-MM-DD(含當天)或 'YYYY-MM-DD HH:MM'；晚於此時的文件不會被檢索")
    a = ap.parse_args()

    docs, mat = load()
    if not docs:
        print("語料庫是空的,請先跑 stockrag_ingest.py")
        return
    hl = 10**9 if a.no_decay else a.half_life
    as_of = parse_as_of(a.as_of) if a.as_of else None
    for i, r in enumerate(search(a.query, docs, mat, a.k, a.kind, hl, as_of=as_of), 1):
        dd = r.get("doc_date")
        ds = dd.strftime("%Y-%m-%d") if isinstance(dd, datetime) else "?"
        print(f"\n[{i}] {r['title']}  ({r['kind']}, {ds}, {r['age_days']} 天前)")
        print(f"    {r['path']}#chunk{r['chunk_idx']}  "
              f"score={r['score']:.5f}  cos={r['vec_sim']:.3f}")
        print(f"    {' '.join(r['content'].split())[:220]}...")


if __name__ == "__main__":
    main()
