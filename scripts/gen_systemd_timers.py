#!/usr/bin/env python3
"""從 deploy/crontab.txt 產生 systemd user timer 單元(Persistent=true)。

動機:vanilla cron 不補跑錯過的任務。主機停機若跨越「每週一次」或「每月」的排程窗口,
該週期整個消失(見 2026-09 tdcc_shareholding 事件:主機 09-15~09-19 停機,週六 13:00
排程從未觸發)。systemd timer 的 `Persistent=true` 會在開機後自動補跑錯過的任務。

只遷「downtime-敏感」者:單一星期幾(每週一次)或每月固定日。每工作日(dow=1-5)類
會隔日自癒,留在 cron。

用法:python scripts/gen_systemd_timers.py   → 產生檔案到 deploy/systemd/
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRONTAB = ROOT / "deploy" / "crontab.txt"
OUT = ROOT / "deploy" / "systemd"

# 只遷這些(單週一次 + 每月);每工作日類自癒,不遷。
SELECTED = {
    # weekly（單一 dow）
    "weekly_outstanding_shares", "weekly_team_verify", "weekly_team_full",
    "data_health_weekly_finmind", "verify_backup_weekly", "tdcc_shareholding",
    "weekly_media_news", "history_continuity", "evening_data_check",
    "weekly_corp_actions", "foreign_shareholding_weekly", "weekly_rag_ingest",
    "requirement_weekly_summary",
    # monthly（固定 dom）
    "macro_signal_reminder", "monthly_revenue_sync",
    "quarterly_earnings_sync", "monthly_verdict_sli",
}
DOW = {"0": "Sun", "7": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
       "4": "Thu", "5": "Fri", "6": "Sat"}


def to_oncalendar(mi: str, h: str, dom: str, dow: str) -> str:
    hm = f"{int(h):02d}:{int(mi):02d}:00"
    if dow != "*":
        days = ",".join(DOW[d] for d in dow.split(","))
        return f"{days} *-*-* {hm}"
    # monthly（dom 可為逗號多值,已在呼叫端合併）
    return f"*-*-{dom} {hm}"


def parse():
    """回 {name: {"cmd": str, "oncalendars": [str,...]}}(同名多行合併 OnCalendar)。"""
    jobs: dict[str, dict] = {}
    for ln in CRONTAB.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" in (ln.split(" ", 1)[0]):
            continue
        m = re.match(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)", ln)
        if not m:
            continue
        mi, h, dom, mon, dow, rest = m.groups()
        name = rest.split("#")[-1].strip() if "#" in rest else None
        if name not in SELECTED:
            continue
        cmd = rest.split("#")[0].strip()
        # 去掉開頭的 `cd <dir> && `(改用 WorkingDirectory)
        cmd = re.sub(r"^cd\s+\S+\s+&&\s+", "", cmd)
        oc = to_oncalendar(mi, h, dom, dow)
        j = jobs.setdefault(name, {"cmd": cmd, "oncalendars": []})
        j["oncalendars"].append(oc)
    return jobs


SERVICE_TMPL = """\
[Unit]
Description=tw-stock {name}（cron→systemd 遷移,Persistent 補跑）
After=network-online.target mongod.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/mdsadmin/Stock/tw-stock-analysis
# 保留原 cron 指令(含 >> logs 重導),行為等價
ExecStart=/usr/bin/bash -c {cmd_quoted}
"""

TIMER_TMPL = """\
[Unit]
Description=Timer: tw-stock {name}

[Timer]
{oncalendar_lines}
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
"""


def sh_squote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = parse()
    names = []
    for name, j in sorted(jobs.items()):
        unit = f"tw-{name.replace('_', '-')}"
        (OUT / f"{unit}.service").write_text(
            SERVICE_TMPL.format(name=name, cmd_quoted=sh_squote(j["cmd"])),
            encoding="utf-8")
        oc_lines = "\n".join(f"OnCalendar={o}" for o in j["oncalendars"])
        (OUT / f"{unit}.timer").write_text(
            TIMER_TMPL.format(name=name, oncalendar_lines=oc_lines), encoding="utf-8")
        names.append((unit, name, j["oncalendars"]))
    # 索引 + 安裝腳本
    print(f"產生 {len(names)} 組單元到 {OUT}:")
    for unit, name, ocs in names:
        print(f"  {unit:<34} {' ; '.join(ocs)}")
    return names


if __name__ == "__main__":
    main()
