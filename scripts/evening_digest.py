#!/usr/bin/env python3
"""
收盤後通知彙整（降噪）
=====================
收盤後各分析腳本以 LINE_SPOOL 模式執行 → 不即時發，改把訊息暫存到 spool 檔。
本腳本在全部分析跑完後執行：讀 spool → 依主題分類 → 每則來源濃縮（表頭+前幾行）
→ 彙整成 2-3 則統一推播，把 ~15 則降到 2-3 則。完整明細仍在 dashboard(:8501)/CSV。

分三主題（固定順序）：
  ① 持倉/風險   北大四大法則日檢、止損清單、價格跌破、資料完整度
  ② 選股機會   團隊分析、選股推薦、存股法、存股成長、品質成長、阿甘投資法
  ③ 量價/籌碼   全市場量價掃描、主力散戶籌碼、量價×籌碼雙訊號、OBV底部背離

用法：
    LINE_SPOOL=/path/spool.jsonl python3 scripts/evening_digest.py            # 讀預設spool→發
    python3 scripts/evening_digest.py --spool /path/spool.jsonl --dry-run     # 只印不發
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 主題路由：命中任一關鍵字（比對訊息前 120 字）即歸入該主題。順序即輸出順序。
THEMES = [
    ("🧭 持倉/風險", [
        "北大四大法則", "持倉風控", "止損檢查", "今日警報摘要", "價格跌破", "資料完整度",
        "資料自癒", "自癒後", "自癒完成",
    ]),
    ("💡 選股機會", [
        "團隊分析", "選股推薦", "存股法", "存股成長", "品質成長", "阿甘投資法",
        "謝富旭", "護城河",
    ]),
    ("📊 量價/籌碼", [
        "量價掃描", "主力/散戶籌碼", "籌碼研判", "雙訊號", "量價×籌碼", "OBV", "底部背離",
    ]),
]

PER_SOURCE_LINES = 10      # 每則來源濃縮保留的內容行數（表頭另計）
MSG_CAP = 4900             # 單則 LINE 上限（保守，<5000）


def _route(body: str) -> int:
    head = body[:120]
    for i, (_, kws) in enumerate(THEMES):
        if any(k in head for k in kws):
            return i
    return -1


def _condense(body: str) -> str:
    """濃縮單則：表頭 + 前 PER_SOURCE_LINES 行內容，其餘略。"""
    lines = [ln for ln in body.splitlines() if ln.strip() != ""]
    if not lines:
        return ""
    head, rest = lines[0], lines[1:]
    kept = rest[:PER_SOURCE_LINES]
    out = [head] + kept
    if len(rest) > PER_SOURCE_LINES:
        out.append(f"  …另 {len(rest) - PER_SOURCE_LINES} 行（完整見 :8501 / CSV）")
    return "\n".join(out)


MERGE = [[0, 1], [2]]   # 持倉風險 + 選股機會 併一則；量價/籌碼 獨立（3 則→2 則降量）


def _cap(body):
    if len(body) > MSG_CAP:
        return body[:MSG_CAP - 20].rstrip() + "\n…（超出略，見 :8501）"
    return body


def build_digests(entries: list[dict]) -> list[str]:
    buckets: list[list[str]] = [[] for _ in THEMES]
    misc: list[str] = []
    for e in entries:
        body = (e.get("body") or "").strip()
        if not body:
            continue
        idx = _route(body)
        (buckets[idx] if idx >= 0 else misc).append(_condense(body))

    date_str = datetime.now().strftime("%m/%d")
    msgs = []
    for group in MERGE:
        secs = [(THEMES[i][0] + "\n" + "\u2500" * 18 + "\n" + "\n\n".join(buckets[i]))
                for i in group if buckets[i]]
        if not secs:
            continue
        if len(secs) > 1:
            combined = "\U0001f4ee 收盤彙整 " + date_str + "\n\n" + "\n\n".join(secs)
            if len(combined) <= MSG_CAP:
                msgs.append(combined)          # 正常：併成一則
            else:
                for sec in secs:               # 爆量：拆回各主題,避免截掉 dailypicks 等
                    msgs.append(_cap(date_str + " 收盤彙整\n\n" + sec))
        else:
            msgs.append(_cap(date_str + " 收盤彙整\n\n" + secs[0]))

    if misc:
        mbody = "\U0001f539 其他  " + date_str + "\n" + "\u2500" * 18 + "\n" + "\n\n".join(misc)
        if msgs and len(msgs[-1]) + len(mbody) + 2 <= MSG_CAP:
            msgs[-1] = msgs[-1] + "\n\n" + mbody
        else:
            msgs.append(_cap(mbody))
    return msgs


def build_full_sections(entries):
    """依主題分組,保留**完整未濃縮**內容(網頁用,無字數限制)。"""
    buckets = [[] for _ in THEMES]
    misc = []
    for e in entries:
        body = (e.get("body") or "").strip()
        if not body:
            continue
        idx = _route(body)
        (buckets[idx] if idx >= 0 else misc).append(body)
    sections = []
    for i, (name, _) in enumerate(THEMES):
        if buckets[i]:
            sections.append({"theme": name, "sources": buckets[i]})
    if misc:
        sections.append({"theme": "\U0001f539 其他", "sources": misc})
    return sections


def _persist(msgs, entries, sent_ok=None):
    """把彙整訊息落地 digest_history,供 dashboard「每日快訊」查閱(即使 LINE 發不出去)。"""
    try:
        from pymongo import MongoClient
        now = datetime.now()
        day = datetime(now.year, now.month, now.day)
        db = MongoClient("localhost", 27017)["tw_stock_analysis"]
        db.digest_history.update_one(
            {"date_str": day.strftime("%Y-%m-%d")},
            {"$set": {
                "date": day,
                "date_str": day.strftime("%Y-%m-%d"),
                "generated_at": now,
                "entry_count": len(entries),
                "messages": [{"seq": i, "text": m, "chars": len(m)}
                             for i, m in enumerate(msgs, 1)],
                "full_sections": build_full_sections(entries),
                "sent_ok": sent_ok,
            }},
            upsert=True,
        )
        print(f"📥 digest 已落地 digest_history（{day.strftime('%Y-%m-%d')}, {len(msgs)} 則）")
    except Exception as e:
        print(f"⚠️ digest 落地失敗（不影響推播）: {e}")


def main():
    ap = argparse.ArgumentParser(description="收盤後通知彙整降噪")
    ap.add_argument("--spool", default=os.getenv("LINE_SPOOL"),
                    help="spool 檔路徑（預設讀 LINE_SPOOL 環境變數）")
    ap.add_argument("--dry-run", action="store_true", help="只印不發、不清 spool")
    args = ap.parse_args()

    if not args.spool:
        print("⚠️ 未指定 --spool 或 LINE_SPOOL"); return
    sp = Path(args.spool)
    if not sp.exists():
        print(f"（spool 不存在，無事可做）: {sp}"); return

    entries = []
    for line in sp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"body": line})   # 容錯：非 JSON 行當純文字

    if not entries:
        print("（spool 為空）"); return

    msgs = build_digests(entries)
    print(f"讀入 {len(entries)} 則 → 彙整成 {len(msgs)} 則")
    _persist(msgs, entries)   # 先落地,LINE 發不出去也留存(含完整內容)

    if args.dry_run:
        for i, m in enumerate(msgs, 1):
            print(f"\n========== 彙整訊息 {i}/{len(msgs)}（{len(m)} 字）==========")
            print(m)
        return

    # 實發：務必確保自己不在 spool 模式（否則會把彙整again寫回 spool）
    os.environ.pop("LINE_SPOOL", None)
    # cron 環境不帶 .env → 沒這行 LineNotifier 拿不到 token、靜默走「未設定」不發。
    from dotenv import load_dotenv
    load_dotenv(str(ROOT / ".env"))
    from src.alerts.line_notifier import LineNotifier
    ln = LineNotifier()
    if not ln.enabled:
        print("⚠️ LINE 未設定，改印出"); [print(m, "\n---") for m in msgs]; return
    ok = sum(1 for m in msgs if ln.send(m))
    print(f"✅ 已發送 {ok}/{len(msgs)} 則")
    _persist(msgs, entries, sent_ok=ok)   # 更新發送結果

    # 歸檔 spool（保留稽核，不直接刪）
    archived = sp.with_name(sp.name + "." + datetime.now().strftime("%Y%m%d_%H%M%S") + ".done")
    try:
        sp.rename(archived)
        print(f"spool 已歸檔 → {archived.name}")
    except OSError as e:
        print(f"⚠️ spool 歸檔失敗（不影響推播）: {e}")


if __name__ == "__main__":
    main()
