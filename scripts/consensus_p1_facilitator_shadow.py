#!/usr/bin/env python3
"""P1 facilitator 影子驗證 — 量「壞票守門」對 facilitator 定案的真實變動率。

只讀 + 呼叫 facilitator LLM 兩次(A=原票/原tally,B=剔壞票/clean tally),比較定案。
data_summary 由 stored reports 重建 —— A/B 一致即可正確量 P1 的 delta(不必等於歷史原值)。
絕不寫 live;僅印報告 / 選擇性寫 log。

安全前置閘門:nightly 在跑 或 .28 GPU 過載 → 拒跑(保護 live 分析)。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from src.moe.consensus import (  # noqa: E402
    is_hollow_reason, _extract_vote, _fmt_transcript, VOTES,
    FACILITATOR_MODEL, FACILITATOR_URL,
)

ROLE_LABEL = {"macro-analyst": "總經", "technical-analyst": "技術",
              "fundamental-analyst": "基本面", "value-analyst": "價值",
              "risk-manager": "風險", "chip-analyst": "籌碼"}


def preflight(gpu_max=50):
    """nightly 在跑 或 .28 GPU>gpu_max% → 拒跑。回 (ok, 訊息)。"""
    try:
        out = subprocess.run(["pgrep", "-af", "evening_pipeline|team_daily|team_analyze|risk_deliberation"],
                             capture_output=True, text=True).stdout
        busy = [l for l in out.splitlines() if "pgrep" not in l]
        if busy:
            return False, f"nightly/分析進程在跑({len(busy)} 個)→ 拒跑,保護 live"
    except Exception:
        pass
    try:
        g = subprocess.run(["ssh", "-o", "ConnectTimeout=6", "-o", "BatchMode=yes", "172.16.9.28",
                            "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=15).stdout.strip()
        util = int(g.split()[0])
        if util > gpu_max:
            return False, f".28 GPU {util}% > {gpu_max}% → 拒跑,避免污染 live"
        return True, f".28 GPU {util}% 空閒,nightly 未跑 → 可跑"
    except Exception as e:
        return False, f"無法確認 .28 GPU({e})→ 保守拒跑"


def _data_summary(reps: dict) -> str:
    return "\n".join(f"【{ROLE_LABEL.get(r, r)}】{(reps.get(r) or '')[:300]}"
                     for r in ROLE_LABEL if reps.get(r))


def _facilitate_direct(symbol, name, advisor, data, transcript, tally, rounds, timeout=90):
    """直呼 ollama(think:false 加速,不動 live _ask)。回定案票別。"""
    prompt = (f"你是投資決策委員會的主持人。委員們已就 {symbol} {name} 討論了 {rounds} 輪。\n\n"
              f"【主分析師草案】\n{advisor}\n\n【關鍵數據】\n{data}\n\n"
              f"【委員最終討論逐字稿】\n{transcript}\n\n"
              f"【最終票數】買進 {tally['買進']} / 持有 {tally['持有']} / 賣出 {tally['賣出']}\n\n"
              f"請綜合委員的論點與分歧做最終定案(不必盲從多數,若少數意見更有理據可採納)。\n"
              f"第一行只寫「買進」或「持有」或「賣出」;接著 2-3 句說明定案理由。")
    r = requests.post(f"{FACILITATOR_URL}/api/generate",
                      json={"model": FACILITATOR_MODEL, "prompt": prompt,
                            "stream": False, "think": False,
                            "options": {"temperature": 0}}, timeout=timeout)
    return _extract_vote(r.json().get("response", ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="抽樣檔數(含壞票+facilitator源)")
    ap.add_argument("--force", action="store_true", help="略過安全閘門(不建議)")
    args = ap.parse_args()

    ok, msg = (True, "--force") if args.force else preflight()
    print(f"[preflight] {msg}")
    if not ok:
        return 2

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    q = {"consensus.final_source": "facilitator", "consensus.votes": {"$exists": True}, "advisor": {"$exists": True}}
    cands = []
    for d in db.team_analysis.find(q, {"symbol": 1, "name": 1, "advisor": 1, "reports": 1,
                                       "consensus": 1, "final_verdict": 1}).sort("date", -1).limit(3000):
        votes = (d.get("consensus") or {}).get("votes") or []
        if any(is_hollow_reason(v.get("reason")) for v in votes):
            cands.append(d)
        if len(cands) >= args.n:
            break
    print(f"抽樣 {len(cands)} 檔(含壞票 + facilitator 定案)\n")

    a_ne_live = flip = err = 0
    rows = []
    for d in cands:
        votes = (d.get("consensus") or {}).get("votes") or []
        clean = [v for v in votes if v.get("vote") and not is_hollow_reason(v.get("reason"))] or votes
        t_all = {v: sum(1 for x in votes if x.get("vote") == v) for v in VOTES}
        t_cln = {v: sum(1 for x in clean if x.get("vote") == v) for v in VOTES}
        ds = _data_summary(d.get("reports") or {})
        rounds = (d.get("consensus") or {}).get("rounds_run", 1)
        try:
            a = _facilitate_direct(d["symbol"], d.get("name", ""), d.get("advisor", ""),
                                   ds, _fmt_transcript(votes), t_all, rounds)
            b = _facilitate_direct(d["symbol"], d.get("name", ""), d.get("advisor", ""),
                                   ds, _fmt_transcript(clean), t_cln, rounds)
        except Exception as e:
            err += 1
            print(f"  {d['symbol']} ERR {e}")
            continue
        live = (d.get("consensus") or {}).get("final")
        if a != live:
            a_ne_live += 1
        if a and b and a != b:
            flip += 1
            rows.append(f"  {d['symbol']} {d.get('name','')}: A(原)={a} → B(剔壞票)={b}  live={live}")
    n = len(cands) - err or 1
    print(f"\n=== P1 facilitator 影子結果(n={len(cands)-err}, err={err}) ===")
    print(f"A(原票重跑) vs live 不一致 : {a_ne_live} ({a_ne_live/n*100:.1f}%)  ← 重建保真度(越低越準)")
    print(f"B(剔壞票) vs A 翻案        : {flip} ({flip/n*100:.1f}%)  ← P1 真實變動率")
    for r in rows:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
