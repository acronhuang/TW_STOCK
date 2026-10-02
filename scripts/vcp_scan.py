#!/usr/bin/env python3
"""VCP 波動收縮形態 —— 每日全市場掃描（併入收盤後管線）。
=========================================================
以 src.morphology.vcp.detect_vcp 掃全市場，將 score≥門檻的候選寫入
`vcp_candidates` 集合（每輪覆蓋），供 dashboard「VCP 候選」頁讀取，
並推一則 LINE 摘要。

用法：
  python scripts/vcp_scan.py              # 掃 + 存 DB + 發 LINE
  python scripts/vcp_scan.py --no-line    # 只掃 + 存 DB，不發
  python scripts/vcp_scan.py --min-score 75
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient

from src.domain.collections import COLL_STOCK_PRICE, COLL_VCP_CANDIDATES
from src.morphology.vcp import screen_vcp_market

MIN_SCORE = 70


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _name_map(db, symbols: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for r in db[COLL_STOCK_PRICE].find(
        {"symbol": {"$in": symbols}, "name": {"$nin": ["", None]}},
        {"_id": 0, "symbol": 1, "name": 1},
    ).sort("date", -1):
        names.setdefault(r["symbol"], r.get("name") or "")
    return names


def persist(db, scan_date, hits: list[dict]) -> None:
    # 只覆蓋同一掃描日，保留歷史快照供日後命中率/回測分析
    db[COLL_VCP_CANDIDATES].delete_many({"scan_date": scan_date})
    if not hits:
        return
    docs = []
    for h in hits:
        docs.append({
            "scan_date": scan_date,
            "symbol": h["symbol"],
            "name": h.get("name", ""),
            "score": h["score"],
            "price": h["price"],
            "pivot": h["pivot"],
            "near_pivot": h["near_pivot"],
            "contractions": h["contractions"],
            "base_depth_pct": h["base_depth_pct"],
            "volume_dryup": h["volume_dryup"],
            "trend_template_passed": h["trend_template"]["passed"],
        })
    db[COLL_VCP_CANDIDATES].insert_many(docs)


def build_line(scan_date, hits: list[dict], top: int = 15) -> str:
    d = scan_date.strftime("%m/%d") if hasattr(scan_date, "strftime") else str(scan_date)[:10]
    L = [f"🌀 VCP 波動收縮候選 ({d})",
         f"  趨勢樣板×逐次收斂×量縮 共 {len(hits)} 檔\n"]
    if not hits:
        L.append("  今日無符合（嚴格訊號，常 0~10 檔）")
    for h in hits[:top]:
        flag = "★突破在即" if h["near_pivot"] else ""
        L.append(f"{h['symbol']} {h.get('name','')} {h['price']:g} "
                 f"分{h['score']} 樞紐{h['pivot']:g} {flag}")
    return "\n".join(L)


def main() -> None:
    no_line = "--no-line" in sys.argv
    min_score = int(_arg("--min-score", str(MIN_SCORE)))
    db = MongoClient("localhost", 27017)["tw_stock_analysis"]

    hits = screen_vcp_market(min_score=min_score)
    syms = [h["symbol"] for h in hits]
    names = _name_map(db, syms)
    for h in hits:
        h["name"] = names.get(h["symbol"], "")

    scan_date = db[COLL_STOCK_PRICE].find_one(sort=[("date", -1)])["date"]
    persist(db, scan_date, hits)

    msg = build_line(scan_date, hits)
    print(msg)
    if not no_line:
        try:
            from pathlib import Path

            from dotenv import load_dotenv
            load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
            from src.alerts.line_notifier import LineNotifier
            ln = LineNotifier()
            if ln.enabled:
                ln.send(msg)
                print("\n✅ LINE 已發送")
            else:
                print("\n⚠️ LINE 未設定")
        except Exception as e:  # noqa: BLE001
            print(f"\n⚠️ LINE 失敗: {e}")


if __name__ == "__main__":
    main()
