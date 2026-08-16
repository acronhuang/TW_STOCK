#!/usr/bin/env python3
"""需求狀態板 —— 跑完所有需求檢查，記錄當前狀態，只在狀態轉變時告警。

用法:
  requirement_status.py              跑全部需求，更新 requirement_status，轉變才告警
  requirement_status.py --dry-run    只跑只印，不寫 DB、不告警
  requirement_status.py --only NFR-OPS-003   只跑指定需求
  requirement_status.py --summary    只印摘要（不重跑檢查），供每週一行提醒

為什麼需要這支（ADR-0009）
--------------------------
檢查結果原本只寫進 schedule_alerts，那是**事件流**不是**狀態**。實測：
`schedule_alerts` 152 則、未解決 152 則、曾被標記已解決 **0 則**——
`resolved` 欄位從未被設為 True，實務上是一個唯附加、永不收斂的串流。
2026-08-15 已修復的 FinMind 402 問題，其 130 則告警至今仍掛在「未解決」。

故分離兩者：
  **狀態**（requirement_status）以需求編號為鍵**覆寫**，回答「現在健康嗎」。
  **告警**（schedule_alerts）只在**狀態轉變時**附加一則，回答「什麼時候變的」。
同一個持續存在的問題只會有一則告警，紅轉綠也會留一則——後者原本完全缺席，
正是 152 則全部掛著的原因。

可失敗性證據（ADR-0002 條件 1，可重跑）:
  正向  requirement_status.py --dry-run                     -> 結束碼 0（全綠時）
  反向  QUAL_TARGET_ANNUAL=5.0 requirement_status.py --dry-run -> 結束碼 1
        （NFR-QUAL 門檻被拉高到必失敗，狀態板應轉紅）

三態沿用各檢查的結束碼：0=pass / 非 0 且非「無資料碼」=fail / 無資料=nodata。
「無資料」不是通過（ADR-0002 條件 2）——它在板上是獨立顏色，不計為達標。
"""
import os
import sys
import argparse
import datetime
import subprocess

from pymongo import MongoClient

ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"
PY = "/home/mdsadmin/Stock/.venv/bin/python3"
DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

# 需求目錄（ADR-0019）。只有列在這裡的才是需求——
# 「做事順便告警」的程式不列入（ADR-0018），它們的健康度由 FR-OUT-001 從外部檢查。
# nodata_codes：該檢查用來表示「無資料」的結束碼，其餘非 0 一律視為未通過。
REQUIREMENTS = [
    dict(id="NFR-CODE-001", name="程式碼迴歸",
         cmd=["bash", "scripts/regression_gate.sh"], nodata_codes=(5,)),
    dict(id="NFR-OPS-001", name="crontab 與版控一致",
         cmd=["bash", "scripts/check_crontab_drift.sh"], nodata_codes=(2,)),
    dict(id="NFR-OPS-002", name="委員會如實投票",
         cmd=[PY, "scripts/committee_live_check.py", "--since-hours", "24"],
         nodata_codes=()),
    dict(id="NFR-OPS-003", name="團隊分析角色失敗率",
         cmd=[PY, "scripts/role_failure_watch.py", "--window", "200"],
         nodata_codes=(2,)),
    dict(id="NFR-DATA-001", name="資料新鮮度",
         cmd=[PY, "scripts/data_freshness_audit.py"], nodata_codes=()),
    dict(id="NFR-DATA-002", name="資料契約",
         cmd=[PY, "scripts/schema_contract_audit.py"], nodata_codes=()),
    dict(id="NFR-QUAL-001", name="判斷品質（短線 5 日）",
         cmd=[PY, "scripts/verdict_orthogonality_backtest.py",
              "--window", "5", "--dry-run"], nodata_codes=(2,)),
    dict(id="NFR-QUAL-002", name="判斷品質（中期 20 日）",
         cmd=[PY, "scripts/verdict_orthogonality_backtest.py",
              "--window", "20", "--dry-run"], nodata_codes=(2,)),
    dict(id="FR-OUT-001", name="對外產出如期產生",
         cmd=[PY, "scripts/output_freshness.py"], nodata_codes=(2,)),
]

ICON = {"pass": "✅", "fail": "🔴", "nodata": "⚪"}
STALE_DAYS = 7          # 週摘要中「已持續超過」的門檻


def run_check(req, timeout=1800):
    """回 (status, exit_code, 最後一行輸出)。"""
    try:
        r = subprocess.run(req["cmd"], cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout)
        rc = r.returncode
        lines = [l for l in (r.stdout + r.stderr).strip().split("\n") if l.strip()]
        tail = lines[-1][:200] if lines else ""
    except subprocess.TimeoutExpired:
        return "fail", -1, f"逾時（>{timeout}s）"
    except Exception as e:
        return "fail", -2, f"執行失敗：{e}"
    if rc == 0:
        return "pass", rc, tail
    if rc in req.get("nodata_codes", ()):
        return "nodata", rc, tail
    return "fail", rc, tail


def record(req, status, rc, detail, now, dry=False):
    """覆寫狀態；回 (前一狀態, 是否轉變)。"""
    col = DB.requirement_status
    prev = col.find_one({"_id": req["id"]}) or {}
    prev_status = prev.get("status")
    changed = prev_status is not None and prev_status != status
    if dry:
        return prev_status, changed
    col.update_one(
        {"_id": req["id"]},
        {"$set": {"requirement": req["id"], "name": req["name"],
                  "check": " ".join(req["cmd"]),
                  "status": status, "exit_code": rc, "detail": detail,
                  "checked_at": now,
                  # since：進入「當前狀態」的時間。狀態沒變就保留原值，
                  # 才能回答「已經紅多久了」——週摘要靠它。
                  "since": now if (changed or prev_status is None)
                           else prev.get("since", now)},
         "$setOnInsert": {"created_at": now}},
        upsert=True)
    return prev_status, changed


def alert_transition(req, prev_status, status, detail, now):
    """只在狀態轉變時寫一則（ADR-0009）。紅轉綠同樣要寫——原本完全缺席。"""
    arrow = f"{ICON.get(prev_status, '?')}{prev_status} → {ICON[status]}{status}"
    level = "info" if status == "pass" else "warning"
    DB.schedule_alerts.create_index([("ts", -1)])
    DB.schedule_alerts.insert_one({
        "ts": now, "level": level, "source": "requirement_status",
        "requirement": req["id"],
        "message": f"{ICON[status]} {req['id']}（{req['name']}）狀態轉變：{arrow}。{detail}",
        "detail": {"requirement": req["id"], "from": prev_status, "to": status},
        "resolved": False})


def summary(now):
    """一行摘要（ADR-0016）：純事件推送的盲點是長期紅著的需求不再產生事件。"""
    rows = list(DB.requirement_status.find({}))
    if not rows:
        print("⚪ requirement_status 尚無資料——需求狀態板還沒跑過")
        return 2
    bad = [r for r in rows if r.get("status") != "pass"]
    stale = [r for r in bad
             if r.get("since") and (now - r["since"]).days >= STALE_DAYS]
    print(f"目前 {len(bad)}/{len(rows)} 條需求未通過"
          f"，其中 {len(stale)} 條已持續超過 {STALE_DAYS} 天")
    for r in sorted(bad, key=lambda x: x.get("since") or now):
        days = (now - r["since"]).days if r.get("since") else 0
        print(f"  {ICON.get(r.get('status'), '?')} {r['_id']:<14} {r.get('name', ''):<20} "
              f"已 {days} 天　{str(r.get('detail', ''))[:52]}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只跑只印，不寫 DB")
    ap.add_argument("--only", help="只跑指定需求編號")
    ap.add_argument("--summary", action="store_true", help="只印摘要，不重跑檢查")
    a = ap.parse_args()
    now = datetime.datetime.now()

    if a.summary:
        return summary(now)

    reqs = [r for r in REQUIREMENTS if not a.only or r["id"] == a.only]
    if not reqs:
        print(f"找不到需求 {a.only}")
        return 2

    print(f"=== 需求狀態板 {now:%Y-%m-%d %H:%M} "
          f"{'(dry-run)' if a.dry_run else ''} ===")
    print("%-14s %-22s %-6s %5s %s" % ("需求", "名稱", "狀態", "碼", "摘要"))
    print("-" * 100)
    n_fail = n_nodata = 0
    for req in reqs:
        status, rc, detail = run_check(req)
        prev, changed = record(req, status, rc, detail, now, a.dry_run)
        if status == "fail":
            n_fail += 1
        elif status == "nodata":
            n_nodata += 1
        mark = "  ← 狀態轉變" if changed else ""
        print("%-14s %-22s %-6s %5s %s%s"
              % (req["id"], req["name"], ICON[status] + status, rc, detail[:44], mark))
        if changed and not a.dry_run:
            alert_transition(req, prev, status, detail, now)

    print()
    print(f"達標 {len(reqs) - n_fail - n_nodata} / 未通過 {n_fail} / 無資料 {n_nodata}"
          f"　（共 {len(reqs)} 條）")
    if n_fail:
        return 1
    if n_nodata:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
