#!/usr/bin/env python3
"""v5 影子 runner — 對『趨勢市買進』重跑 advisor 整合(追高防制 prompt),寫 advisor_v5_rating。

嚴格影子:不動 live verdict/final_verdict/consensus;只新增 shadow 欄。盤整市略過(已達標)。
每檔 1 次 LLM(僅重跑整合,不重跑 6 分析師)。--limit / --dry-run 可控成本。

用法(.166):
    /home/mdsadmin/Stock/.venv/bin/python3 scripts/buyside_shadow_advisor_v5.py --limit 50
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.buyside.regime import classify_regime
from src.analysis.buyside.advisor_v5 import build_advisor_prompt_v5

OLLAMA_28 = os.getenv("OLLAMA_URL", "http://172.16.9.28:11434")
MODEL = os.getenv("OLLAMA_FACILITATOR_MODEL", "qwen3-14b:latest")
_ROLE_LABEL = [("macro-analyst", "總經"), ("fundamental-analyst", "基本面"),
               ("value-analyst", "估值"), ("technical-analyst", "技術"),
               ("chip-analyst", "籌碼"), ("risk-manager", "風險")]
_RATINGS = ("強力買進", "買進", "觀望", "減碼", "賣出")


def advisor_base_prompt(symbol: str, reports: dict) -> str:
    lines = [f"你是投資顧問，整合以下 6 份報告，給 {symbol} 最終建議："]
    for role, label in _ROLE_LABEL:
        lines.append(f"【{label}】{reports.get(role, '無')}")
    lines.append("輸出規則:第一行只輸出 `評級：<X>`,五選一【強力買進/買進/觀望/減碼/賣出】。"
                 "評級需呼應技術型態方向。")
    return "\n".join(lines)


def extract_rating(text: str):
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"評級[：:]\s*(強力買進|買進|觀望|減碼|賣出)", t) \
        or re.search(r"評級[：:]\s*(強力買進|買進|觀望|減碼|賣出)", text or "")
    return m.group(1) if m else None


def default_ask(prompt: str) -> str:
    import requests
    # qwen3 為 thinking model:預算不足會只輸出 <think> 而無評級(~17% None)。
    # 用 ollama 頂層 think=false 硬關思考 → 直接輸出評級,又快又穩(比 /no_think prompt 可靠)。
    def _post(think):
        r = requests.post(f"{OLLAMA_28}/api/generate",
                          json={"model": MODEL, "prompt": prompt, "stream": False,
                                "think": think,
                                "options": {"temperature": 0.1, "num_predict": 320}}, timeout=120)
        return r.json().get("response", "")
    out = _post(False)
    if extract_rating(out) is None:            # 極少數仍缺 → 開 thinking 重試一次(較慢但語意完整)
        out = _post(True)
    return out


def run(db, window: int = 20, limit: int | None = None, dry_run: bool = False,
        ask_fn=None, regime_fn=None, resume: bool = False) -> dict:
    ask = ask_fn or default_ask
    rf = regime_fn or (lambda dt: classify_regime(db, dt))
    n = flipped = skipped_sideways = resumed = 0
    for a in db["team_analysis"].find(
            {"final_verdict": "買進", "reports.technical-analyst": {"$exists": True}},
            {"symbol": 1, "date": 1, "reports": 1, "advisor_v5_rating": 1}):
        if limit and n >= limit:
            break
        if resume and a.get("advisor_v5_rating") is not None:
            resumed += 1                   # 已跑過 → 跳過(可中斷續跑,不白燒 LLM)
            continue
        reg = rf(a.get("date"))
        if reg not in ("多頭", "空頭"):
            skipped_sideways += 1
            continue                       # 盤整/未知 → 維持,不跑(影子只針對趨勢市)
        prompt = build_advisor_prompt_v5(advisor_base_prompt(a["symbol"], a.get("reports", {})), reg)
        rating = extract_rating(ask(prompt))
        if not dry_run:
            db["team_analysis"].update_one(
                {"_id": a["_id"]},
                {"$set": {"advisor_v5_rating": rating, "advisor_v5_regime": reg}})
        n += 1
        if rating and rating not in ("買進", "強力買進"):
            flipped += 1
    return {"n": n, "flipped": flipped, "skipped_sideways": skipped_sideways, "resumed": resumed}


def main() -> int:
    from pymongo import MongoClient
    ap = argparse.ArgumentParser(description="v5 advisor 影子 runner")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true", help="跳過已寫 advisor_v5_rating 者(可中斷續跑)")
    args = ap.parse_args()
    db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017")).tw_stock_analysis
    res = run(db, window=args.window, limit=args.limit, dry_run=args.dry_run, resume=args.resume)
    print(f"[v5-shadow] 趨勢市買進處理 {res['n']}(降級/觀望 {res['flipped']})、"
          f"盤整略過 {res['skipped_sideways']}、續跑略過 {res.get('resumed',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
