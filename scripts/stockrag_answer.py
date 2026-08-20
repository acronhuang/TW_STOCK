#!/usr/bin/env python3
"""股票分析 RAG — 生成(檢索 → LLM 作答,附出處)

Prompt 設計針對本專案語料的特性:
  1. 語料裡有大量**互相矛盾**的舊報告(例:2026-02 說 adj_close 覆蓋率 100% ✅,
     但 2026-07-20 已證實那是假的)。故 prompt 明確要求「日期較新者優先」,
     並在來源分歧時**主動指出**,而不是選一個講。
  2. 一律附上 [n] 出處編號 —— 這個語料不可盡信,使用者必須能回頭查證。
  3. 資料不足時要說「資料不足」,不要用常識補。

模型:qwen2.5-14b(.28 上實測約 25 tok/s)。qwen2.5 系列預設傾向簡體,
故 prompt 明確要求繁體中文。
"""
import json
import sys
import urllib.request
from datetime import datetime

OLLAMA = "http://172.16.9.28:11434"
MODEL = "qwen2.5-14b:latest"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SYSTEM = """你是台股量化分析專案的技術文件助理。只能根據提供的「資料來源」回答。

**輸出規則(務必遵守)**

1. 一律使用**繁體中文**。
2. **每一句陳述後面都必須接出處編號**,格式如:`後復權價不是當日真實成交價 [1]`。
   沒有出處可標的句子就不要寫出來。這是硬性要求,不可省略。
3. 資料來源附有日期。**日期較新的優先** —— 本專案的舊報告有不少結論已被推翻。
4. 若不同來源說法**互相矛盾**,先寫一行「⚠️ 來源不一致」,
   再分別列出各自說法與日期,並指明以較新者為準。不要只挑一個講,也不要自行調和。
5. 資料裡沒提到的內容,**一個字都不要寫**。不要用常識或推測補足。
   若整份資料都與問題無關,就只回:`資料庫中沒有相關內容。`
6. 簡潔。**第一句就是結論**,不要開場白、不要免責聲明、不要重複題目。"""


def build_prompt(question, hits):
    parts = []
    for i, h in enumerate(hits, 1):
        dd = h.get("doc_date")
        ds = dd.strftime("%Y-%m-%d") if isinstance(dd, datetime) else "日期不明"
        age = h.get("age_days", 0)
        flag = "(較舊,可能已過時)" if age > 120 else ""
        parts.append(f"[{i}] 來源:{h['path']} · 日期 {ds}{flag}\n{h['content']}")
    return f"""資料來源:

{chr(10).join(parts)}

---
問題:{question}

請依規則作答。"""


def generate(question, hits, model=MODEL, num_predict=700, timeout=600):
    if not hits:
        return "沒有檢索到相關資料,無法回答。", 0.0
    payload = {
        "model": model,
        "system": SYSTEM,
        "prompt": build_prompt(question, hits),
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": 0.2, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    import time
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d.get("response", "").strip(), time.time() - t


def main():
    import argparse
    sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
    from stockrag_search import load, search

    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=6)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--no-decay", action="store_true")
    a = ap.parse_args()

    docs, mat = load()
    if not docs:
        print("語料庫是空的")
        return
    hits = search(a.question, docs, mat, k=a.k,
                  half_life=10**9 if a.no_decay else 180)
    ans, el = generate(a.question, hits, a.model)

    print(f"\n{ans}\n")
    print("─" * 70)
    print(f"依據 {len(hits)} 段資料,生成耗時 {el:.1f}s")
    for i, h in enumerate(hits, 1):
        dd = h.get("doc_date")
        ds = dd.strftime("%Y-%m-%d") if isinstance(dd, datetime) else "?"
        print(f"  [{i}] {ds}  {h['path']}#chunk{h['chunk_idx']}")


if __name__ == "__main__":
    main()
