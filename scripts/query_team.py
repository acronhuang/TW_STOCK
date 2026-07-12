#!/usr/bin/env python3
"""
團隊分析記錄查詢 CLI（唯讀）。
資料來源：results/team_analysis/team_YYYYMMDD.json

用法：
  query_team.py --list                 列出所有可查日期
  query_team.py 2330                    查 2330 最新一日完整分析
  query_team.py 2330 20260710          查指定日期
  query_team.py --verdicts             最新一日所有標的的合議定案彙總
  query_team.py --verdicts 20260710    指定日期的定案彙總
"""
import glob
import json
import os
import sys

DIR = "/home/mdsadmin/Stock/tw-stock-analysis/results/team_analysis"


def _files():
    fs = sorted(glob.glob(f"{DIR}/team_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json"))
    return fs


def _load(date=None):
    if date:
        p = f"{DIR}/team_{date}.json"
        if not os.path.exists(p):
            print(f"查無 {date} 的記錄"); sys.exit(1)
    else:
        fs = _files()
        if not fs:
            print("查無任何記錄"); sys.exit(1)
        p = fs[-1]
    return os.path.basename(p)[5:13], json.load(open(p, encoding="utf-8"))


def cmd_list():
    for f in _files():
        d = json.load(open(f, encoding="utf-8"))
        ana = d.get("analyses", d if isinstance(d, list) else [])
        n = len(ana)
        adv = sum(1 for a in ana if a.get("advisor"))
        con = sum(1 for a in ana if a.get("consensus"))
        print(f"  {os.path.basename(f)[5:13]}  標的 {n:>5}   顧問 {adv:>5}   合議 {con:>5}")


def cmd_symbol(sym, date):
    ds, d = _load(date)
    a = next((x for x in d["analyses"] if x["symbol"] == sym), None)
    if not a:
        print(f"{ds} 無 {sym}"); return
    name = (d.get("meta", {}).get(sym) or {}).get("name", "")
    print(f"══ {sym} {name}  @ {ds} ══")
    ICON = {"macro-analyst": "🎯總經", "technical-analyst": "📈技術",
            "fundamental-analyst": "💰基本面", "value-analyst": "💎價值",
            "risk-manager": "🛡️風險", "chip-analyst": "🏦籌碼"}
    for role, txt in (a.get("reports") or {}).items():
        print(f"\n{ICON.get(role, role)}")
        print("  " + (txt or "").strip().replace("\n", "\n  "))
    print("\n── 佐證數據 ──")
    for e in a.get("evidence", []):
        print(f"  {e['metric']} = {e.get('db')}  {e.get('flag', '')}")
    if a.get("advisor"):
        print("\n🎩 顧問整合\n  " + a["advisor"].strip().replace("\n", "\n  "))
    c = a.get("consensus")
    if c:
        print(f"\n🗳️ 合議定案: {c.get('final')}  (買{c['tally']['買進']}/持{c['tally']['持有']}/賣{c['tally']['賣出']})")
        for v in c.get("votes", []):
            print(f"    {v['model']}: {v['vote']} — {v.get('reason', '')}")
    else:
        print("\n🗳️ 合議: (未跑 phase2)")


def cmd_verdicts(date):
    ds, d = _load(date)
    rows = []
    for a in d["analyses"]:
        c = a.get("consensus")
        if c:
            rows.append((a["symbol"], c.get("final"), c["tally"]))
    print(f"══ {ds} 合議定案彙總 ══")
    if not rows:
        print("  (此日尚無合議結果 — phase2 未跑)"); return
    from collections import Counter
    cnt = Counter(r[1] for r in rows)
    print(f"  總 {len(rows)} 檔： " + "  ".join(f"{k}={v}" for k, v in cnt.most_common()))
    print()
    for sym, final, t in sorted(rows, key=lambda r: r[1]):
        print(f"  {sym}  {final}  (買{t['買進']}/持{t['持有']}/賣{t['賣出']})")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return
    if a[0] == "--list":
        cmd_list()
    elif a[0] == "--verdicts":
        cmd_verdicts(a[1] if len(a) > 1 else None)
    else:
        cmd_symbol(a[0], a[1] if len(a) > 1 else None)


if __name__ == "__main__":
    main()
