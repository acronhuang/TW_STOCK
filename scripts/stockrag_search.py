#!/usr/bin/env python3
"""股票分析 RAG — 檢索(向量 + 字面 兩路 RRF,加時間衰減)

時間衰減是這套設計的重點:專案內 124 份根目錄報告彼此矛盾,不少結論已被推翻 ——
例如 2026-02 的驗證報告說「adj_close 覆蓋率 100% ✅」,但 2026-07-20 已證實那是假的。
不做時間加權,問「adj_close 正常嗎」就會拿到舊報告的錯誤答案。

    score = RRF(向量排名, 字面排名) × 0.5^(文件年齡 / 半衰期)

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

OLLAMA = "http://172.16.9.28:11434"
MODEL = "bge-m3"
RRF_K = 60
HALF_LIFE = 180        # 天

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def embed(text):
    req = urllib.request.Request(
        f"{OLLAMA}/api/embeddings",
        data=json.dumps({"model": MODEL, "prompt": text}).encode(),
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


def search(query, docs, mat, k=5, kind=None, half_life=HALF_LIFE, pool=60):
    qv = np.array(embed(query), dtype=np.float32)
    qv /= (np.linalg.norm(qv) + 1e-9)

    mask = np.ones(len(docs), dtype=bool)
    if kind:
        mask = np.array([d.get("kind") == kind for d in docs])
    idx_all = np.where(mask)[0]
    if idx_all.size == 0:
        return []

    vec = mat[idx_all] @ qv                       # cosine
    lit = literal_scores(query, [docs[i] for i in idx_all])

    top_v = idx_all[np.argsort(-vec)[:pool]]
    top_l = idx_all[np.argsort(-lit)[:pool]]

    rank_v = {gi: r + 1 for r, gi in enumerate(top_v)}
    rank_l = {gi: r + 1 for r, gi in enumerate(top_l)}

    now = datetime.now()
    fused = []
    for gi in set(rank_v) | set(rank_l):
        rrf = (1.0 / (RRF_K + rank_v[gi]) if gi in rank_v else 0.0) + \
              (1.0 / (RRF_K + rank_l[gi]) if gi in rank_l else 0.0)
        d = docs[gi]
        dd = d.get("doc_date")
        age = (now - dd).days if isinstance(dd, datetime) else 0
        decay = 0.5 ** (age / float(half_life)) if half_life < 10**8 else 1.0
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
    a = ap.parse_args()

    docs, mat = load()
    if not docs:
        print("語料庫是空的,請先跑 stockrag_ingest.py")
        return
    hl = 10**9 if a.no_decay else a.half_life
    for i, r in enumerate(search(a.query, docs, mat, a.k, a.kind, hl), 1):
        dd = r.get("doc_date")
        ds = dd.strftime("%Y-%m-%d") if isinstance(dd, datetime) else "?"
        print(f"\n[{i}] {r['title']}  ({r['kind']}, {ds}, {r['age_days']} 天前)")
        print(f"    {r['path']}#chunk{r['chunk_idx']}  "
              f"score={r['score']:.5f}  cos={r['vec_sim']:.3f}")
        print(f"    {' '.join(r['content'].split())[:220]}...")


if __name__ == "__main__":
    main()
