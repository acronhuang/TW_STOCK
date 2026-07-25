#!/usr/bin/env python3
"""股票分析 RAG — ingest(在 .166 本機執行,寫入 MongoDB)

為什麼用 MongoDB + numpy 而不是 pgvector:
  .166 沒有 docker、沒有 postgres、也沒有免密 sudo,裝不了 pgvector。
  但語料只有約 3,800 塊 × 1024 維 ≈ 15MB,載進記憶體做一次矩陣乘法即可,
  暴力 cosine 約數毫秒 —— 這個規模不需要向量索引。
  ⚠️ 這個作法約在 10 萬塊以上會開始吃力,屆時才需要換真正的向量資料庫。

嵌入用 bge-m3(1024 維,多語)。不用 nomic-embed-text —— 那是 768 維英文向,
對繁中語料檢索品質明顯較差。

Ollama(.28)是 CPU 推論且與資安 RAG 共用,故預設限速。
"""
import argparse
import hashlib
import json
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient, UpdateOne

ROOT = Path("/home/mdsadmin/Stock/tw-stock-analysis")
OLLAMA = "http://172.16.9.28:11434"
MODEL = "bge-m3"
DIM = 1024
CHUNK, OVERLAP = 800, 150
MAX_CHUNKS_PER_DOC = 120     # 單檔塊數上限:防止一份大檔淹沒整個語料
MAX_JSON_BYTES = 300_000     # result JSON 超過此大小視為原始資料傾印,不逐塊 ingest


def embed(text):
    req = urllib.request.Request(
        f"{OLLAMA}/api/embeddings",
        data=json.dumps({"model": MODEL, "prompt": text[:6000]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                v = json.loads(r.read()).get("embedding") or []
                if len(v) == DIM:
                    return v
                raise ValueError(f"維度 {len(v)}")
        except Exception:
            if a == 2:
                raise
            time.sleep(3 * (a + 1))


def collect():
    out = []
    for p in sorted(ROOT.glob("*.md")):
        out.append(("report", p))
    for p in sorted(ROOT.glob("docs/**/*.md")):
        out.append(("doc", p))
    for p in sorted(ROOT.glob("results/**/*.json")):
        # team_analysis 等每日輸出是整個台股(近 2000 檔)的逐檔傾印,
        # 15MB 一份、當純文字會切成上萬塊、淹沒真正有價值的診斷文件。
        # 這類原始資料不適合逐塊 ingest;超過門檻直接跳過。
        if p.stat().st_size > MAX_JSON_BYTES:
            print(f"  略過大 JSON({p.stat().st_size//1024}KB): {p.relative_to(ROOT)}", flush=True)
            continue
        out.append(("result", p))
    return out


def chunks(text):
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    cs = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK - OVERLAP)]
    if len(cs) > MAX_CHUNKS_PER_DOC:
        # 保底防呆:單檔仍過大就截斷,避免任何一份檔案主宰檢索結果
        print(f"  ⚠️ 切塊 {len(cs)} 超過上限,截斷為 {MAX_CHUNKS_PER_DOC}", flush=True)
        cs = cs[:MAX_CHUNKS_PER_DOC]
    return cs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=99999)
    ap.add_argument("--sleep", type=float, default=0.05,
                    help="每塊間停頓,避免嵌入把 CPU 佔滿影響資安 RAG")
    ap.add_argument("--resume", action="store_true", help="跳過內容未變的檔案")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["stockrag"]
    col = db.docs
    col.create_index([("path", 1), ("chunk_idx", 1)], unique=True)
    col.create_index([("doc_date", -1)])
    col.create_index([("kind", 1)])

    files = collect()[:args.limit]
    print(f"語料 {len(files)} 份", flush=True)

    seen = {}
    if args.resume:
        seen = {d["_id"]: d["sha"] for d in col.aggregate(
            [{"$group": {"_id": "$path", "sha": {"$first": "$sha"}}}])}
        print(f"續跑:已有 {len(seen)} 份", flush=True)

    nf = nc = 0
    for kind, p in files:
        rel = str(p.relative_to(ROOT))
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not body.strip():
            continue
        sha = hashlib.sha1(body.encode("utf-8", "replace")).hexdigest()
        if args.resume and seen.get(rel) == sha:
            continue

        title = next((l.lstrip("# ").strip() for l in body.splitlines()
                      if l.strip().startswith("#")), p.name)
        mt = datetime.fromtimestamp(p.stat().st_mtime)
        cs = chunks(body)

        col.delete_many({"path": rel})
        ops = []
        for i, c in enumerate(cs):
            try:
                v = embed(c)
            except Exception as e:
                print(f"  ! {rel}#{i}: {str(e)[:60]}", flush=True)
                continue
            ops.append(UpdateOne(
                {"path": rel, "chunk_idx": i},
                {"$set": {"content": c, "embedding": v, "doc_date": mt,
                          "kind": kind, "title": title[:200], "sha": sha,
                          "updated_at": datetime.now()}}, upsert=True))
            nc += 1
            time.sleep(args.sleep)
        if ops:
            col.bulk_write(ops, ordered=False)
        nf += 1
        if nf % 10 == 0:
            print(f"  … {nf}/{len(files)} 份,{nc} 塊", flush=True)

    print(f"\n完成:本次 {nf} 份 / {nc} 塊;"
          f"庫內共 {col.count_documents({}):,} 塊 / "
          f"{len(col.distinct('path'))} 份", flush=True)


if __name__ == "__main__":
    main()
