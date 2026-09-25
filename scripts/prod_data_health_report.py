#!/usr/bin/env python3
"""prod_data 定期真實庫驗證 —— 排程入口(.166)。

為什麼:`prod_data` 測試斷言「真實世界的事實」(台積電評等/EPS、半導體同業數、
10 萬筆規模/新鮮度…),依 ADR-0011 刻意排除於 CI(合成種子造假既脆又違規)。
但這些不變式仍需被守住 —— 差別在於它們只對 live 正式庫有意義。本腳本在 .166
以真實 `tw_stock_analysis` 定期跑一次,把結果寫成報告 + 歷史快照,異常才發告警。

輸出:
  - logs/prod_data_report_<date>.md  逐測 pass/fail/skip + 失敗訊息
  - prod_data_health_history 集合:每次一筆快照(唯讀主資料,只寫自己的歷史集合)
  - --alert:有 fail/error 才寫 schedule_alerts(網頁🔔可見),對齊 data_health_check

用法(建議 cron 每日一次,盤後):
    cd /home/mdsadmin/Stock/tw-stock-analysis && \\
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/prod_data_health_report.py --alert

退場碼:一律 0(排程用告警而非硬失敗);腳本自身錯誤才非 0。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "prod_data_health_report"

# 失敗初步分類啟發式(僅供參考,仍需人工三分;見 tests/README runbook)。
# 以「檔名」為主(最可靠),「失敗訊息關鍵字」為覆寫(新鮮度/筆數→資料類)。
DATA_FILES = ("test_data_integrity",)
FACT_FILES = ("test_financial_health", "test_peer_comparison", "test_stock_ranker", "test_ranking_steps")
DATA_HINTS = ("距今", "日期距", "筆數", "新鮮", "覆蓋", "股票數", "比例過高", "資料不足")
FACT_HINTS = ("grade", "ROE", "EPS", "產業", "同業", "半導體", "評等")
CLASS_LABEL = {"data": "📉 資料管線", "fact": "🌍 世界事實", "code": "🔴 程式回歸"}


def classify(test: str, detail: str) -> str:
    """回 "data" / "fact" / "code"(初步分類,人工三分的起點)。"""
    if any(h in detail for h in DATA_HINTS):        # 新鮮度/筆數類訊息 → 資料優先
        return "data"
    if any(f in test for f in DATA_FILES):
        return "data"
    if any(f in test for f in FACT_FILES) or any(h in detail for h in FACT_HINTS):
        return "fact"
    return "code"


def run_pytest(marker: str, junit_path: Path) -> int:
    """在真實庫上跑指定 marker 的測試,結果寫 junit xml。回傳 pytest 退場碼。"""
    return subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-m", marker,
            "-o", "addopts=",              # 清掉 pytest.ini 的 -v,加速且輸出乾淨
            "-p", "no:cacheprovider",
            "--tb=line", "-q",
            f"--junitxml={junit_path}",
        ],
        cwd=str(ROOT),
    ).returncode


def parse_junit(junit_path: Path) -> dict:
    """解析 junit xml → 逐測結果與統計。"""
    root = ET.parse(junit_path).getroot()
    suites = root.findall(".//testsuite") or [root]
    cases: list[dict] = []
    for suite in suites:
        for tc in suite.findall("testcase"):
            name = f"{tc.get('classname', '')}::{tc.get('name', '')}".strip(":")
            status, detail = "passed", ""
            for tag in ("failure", "error", "skipped"):
                el = tc.find(tag)
                if el is not None:
                    status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                    detail = (el.get("message") or el.text or "").strip().splitlines()[0][:300] \
                        if (el.get("message") or el.text) else ""
                    break
            cases.append({
                "test": name,
                "status": status,
                "time": float(tc.get("time", 0) or 0),
                "detail": detail,
                "triage": classify(name, detail) if status in ("failed", "error") else "",
            })
    counts = {k: sum(1 for c in cases if c["status"] == k)
              for k in ("passed", "failed", "error", "skipped")}
    counts["total"] = len(cases)
    return {"counts": counts, "cases": cases}


def to_markdown(result: dict, now: datetime, marker: str) -> str:
    c = result["counts"]
    ok = c["failed"] == 0 and c["error"] == 0
    head = "✅ 全部通過" if ok else f"🔴 {c['failed']} failed / {c['error']} error"
    lines = [
        f"# prod_data 真實庫驗證報告 — {now:%Y-%m-%d %H:%M}",
        "",
        f"- 標記(marker):`{marker}`",
        f"- 結果:**{head}**",
        f"- 統計:total {c['total']} · passed {c['passed']} · failed {c['failed']} "
        f"· error {c['error']} · skipped {c['skipped']}",
    ]
    # 失敗初步三分統計(📉資料 / 🌍事實 / 🔴程式)
    tri = {k: sum(1 for x in result["cases"]
                  if x["status"] in ("failed", "error") and x.get("triage") == k)
           for k in ("data", "fact", "code")}
    if sum(tri.values()):
        lines.append("- 初步分類(僅參考,仍需人工三分):"
                     + " · ".join(f"{CLASS_LABEL[k]} {v}" for k, v in tri.items() if v))
    lines += [
        "",
        "| 測試 | 狀態 | 初步分類 | 秒 | 訊息 |",
        "|---|---|---|--:|---|",
    ]
    order = {"failed": 0, "error": 1, "skipped": 2, "passed": 3}
    emoji = {"passed": "✅", "failed": "🔴", "error": "💥", "skipped": "⏭️"}
    for cse in sorted(result["cases"], key=lambda x: (order.get(x["status"], 9), x["test"])):
        msg = cse["detail"].replace("|", "\\|") if cse["detail"] else ""
        tri_lbl = CLASS_LABEL.get(cse.get("triage", ""), "")
        lines.append(f"| {cse['test']} | {emoji.get(cse['status'],'?')} {cse['status']} "
                     f"| {tri_lbl} | {cse['time']:.1f} | {msg} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="prod_data 真實庫驗證報告")
    ap.add_argument("--marker", default="prod_data", help="要跑的 pytest marker(預設 prod_data)")
    ap.add_argument("--alert", action="store_true", help="有 fail/error 才寫 schedule_alerts")
    ap.add_argument("--no-db", action="store_true", help="不寫任何 DB(僅產生報告檔,供本機測試)")
    args = ap.parse_args()

    now = datetime.now()
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        junit_path = Path(tf.name)
    try:
        rc = run_pytest(args.marker, junit_path)
        if not junit_path.exists() or junit_path.stat().st_size == 0:
            print(f"💥 pytest 未產生 junit 報告(rc={rc});疑似收集期錯誤。")
            return 1
        result = parse_junit(junit_path)
    finally:
        junit_path.unlink(missing_ok=True)

    c = result["counts"]
    ok = c["failed"] == 0 and c["error"] == 0

    # 報告檔
    report_md = to_markdown(result, now, args.marker)
    report_file = logs_dir / f"prod_data_report_{now:%Y%m%d}.md"
    report_file.write_text(report_md, encoding="utf-8")

    # 摘要(cron log 可見)
    verdict = "✅ 全過" if ok else f"🔴 {c['failed']} failed / {c['error']} error"
    print(f"[{now:%Y-%m-%d %H:%M}] prod_data 驗證:{verdict}"
          f" · total {c['total']} passed {c['passed']} skipped {c['skipped']}")
    print(f"報告:{report_file}")
    for cse in result["cases"]:
        if cse["status"] in ("failed", "error"):
            print(f"  - [{CLASS_LABEL.get(cse.get('triage',''),'?')}] "
                  f"{cse['status'].upper()} {cse['test']}: {cse['detail']}")

    if args.no_db:
        return 0

    # 歷史快照 + 告警(只寫自己的歷史集合;唯讀主資料)
    try:
        from src.config import get_db
        from src.domain.collections import COLL_SCHEDULE_ALERTS
        db = get_db()
        db["prod_data_health_history"].insert_one({
            "ts": now, "source": SOURCE, "marker": args.marker,
            "ok": ok, "counts": c,
            "failures": [x for x in result["cases"] if x["status"] in ("failed", "error")],
        })
        if args.alert and not ok:
            db[COLL_SCHEDULE_ALERTS].insert_one({
                "ts": now, "level": "warning", "source": SOURCE,
                "message": f"prod_data 真實庫驗證異常:{c['failed']} failed / {c['error']} error",
                "detail": {"counts": c,
                           "failures": [f"[{CLASS_LABEL.get(x.get('triage',''),'?')}] {x['test']}: {x['detail']}"
                                        for x in result["cases"]
                                        if x["status"] in ("failed", "error")]},
                "resolved": False,
            })
            print("已寫 schedule_alerts(網頁🔔排程警報可查)")
    except Exception as e:  # DB 不可達 → 報告檔仍在,不讓排程硬失敗
        print(f"⚠️ 寫入 DB 失敗(報告檔已產出):{type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
