#!/usr/bin/env python3
"""研究方法論自動週報 —— 回測 / Walk-Forward / 前視洩漏驗證（Skill 步驟 11）。

跑 run_ab_robust.py（quality A/B 三組對照 + 覆蓋率閘門 + 前視洩漏判定），
把 ab_verdict.txt 落地為帶日期的週報，並推 LINE 摘要。

用法：
    python scripts/weekly_research_report.py            # 預設 --parse-only（輕量，重解析既有 JSON）
    python scripts/weekly_research_report.py --full     # 完整重跑 3 組回測（約數十分鐘，排程用）
    python scripts/weekly_research_report.py --no-line   # 不推 LINE

排程（crontab，週六上午，避開週五團隊週跑）：
    0 10 * * 6  cd /home/mdsadmin/Stock/tw-stock-analysis && \
      /home/mdsadmin/Stock/.venv/bin/python3 scripts/weekly_research_report.py --full \
      >> logs/cron_weekly_research_report.log 2>&1  # weekly_research_report
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

PY = sys.executable
VERDICT = PROJECT_ROOT / "ab_verdict.txt"
REPORTS = PROJECT_ROOT / "reports"


def run_ab(full):
    cmd = [PY, "scripts/run_ab_robust.py"] + ([] if full else ["--parse-only"])
    print(f"[週報] 執行：{' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
                       timeout=5400)
    if r.returncode != 0:
        print(f"[週報] run_ab_robust 非零退出 {r.returncode}：{r.stderr[-300:]}")
    return r.returncode


def line_summary(verdict_text, dstr):
    keep = []
    for ln in verdict_text.splitlines():
        s = ln.strip()
        if any(t in s for t in ("none", "fundamental", "legacy", "洩漏判定",
                                 "PASS", "FAIL", "貢獻", "覆蓋")):
            keep.append(s)
    body = "\n".join(keep[:12])
    return (f"📊 研究方法論週報 {dstr}\n{body}\n"
            "⚠️ 回測結果不代表未來；研究名單 ≠ 買進名單")


def main():
    full = "--full" in sys.argv
    no_line = "--no-line" in sys.argv
    dstr = datetime.now().strftime("%Y-%m-%d")

    run_ab(full)

    if not VERDICT.exists():
        print("[週報] 找不到 ab_verdict.txt，中止")
        sys.exit(1)
    text = VERDICT.read_text(encoding="utf-8")

    REPORTS.mkdir(exist_ok=True)
    report = REPORTS / f"research_validation_{dstr}.md"
    report.write_text(
        f"# 研究方法論驗證週報 {dstr}\n\n"
        f"> 回測 / Walk-Forward / 前視洩漏（Skill 步驟 11）。{'完整重跑' if full else 'parse-only'}。\n\n"
        "```\n" + text + "\n```\n\n"
        "判讀：quality 貢獻為正且洩漏判定 PASS → 多因子優勢穩健，🟢 名單可信；"
        "若 FAIL 或貢獻轉負 → 🟢 名單降級為僅供觀察。回測結果不代表未來。\n",
        encoding="utf-8")
    print(f"[週報] 已寫出 {report}")

    if not no_line:
        from src.alerts.line_notifier import LineNotifier
        ok = LineNotifier().send(line_summary(text, dstr))
        print(f"[LINE] {'已送出/暫存' if ok else '未發送（未設定或停用）'}")


if __name__ == "__main__":
    main()
