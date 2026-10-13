#!/usr/bin/env python3
"""合議軌跡報表（唯讀）：最近幾天團隊分析紀錄的角色覆蓋、失敗角色、票數、輪數、空洞投票。

用法：python scripts/verdict_trajectory_report.py [--days 2] [--strict]
--strict：只要有任何一筆違規（缺角色、角色失敗、票數不足、空洞投票）就以非零狀態結束；預設只印報表。
"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis import verdict_trajectory as vt  # noqa: E402


def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def render(summary: dict, limit: int = 10) -> str:
    lines = [f"紀錄 {summary['records']} 筆（有合議 {summary['with_consensus']}）",
             f"角色覆蓋 {pct(summary['role_hit_rate'])}；有失敗角色的紀錄 {summary['records_with_failed_role']}",
             f"委員票數不足 {summary['vote_shortfall']}；有空洞投票的紀錄 {summary['hollow_vote_records']}",
             f"進到第二輪 {pct(summary['two_round_share'])}；有異議 {pct(summary['dissent_share'])}",
             f"違規 {len(summary['violating'])} 筆"]
    for run in summary["violating"][:limit]:
        lines.append(f"  {run['symbol']}：{'；'.join(run['violations'])}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    from src.config import get_db
    col = get_db()["team_analysis"]
    newest = col.find_one(sort=[("created_at", -1)])
    if not newest:
        print("team_analysis 是空的")
        return 1
    docs = list(col.find({"created_at": {"$gte": newest["created_at"] - timedelta(days=args.days)}}))
    summary = vt.summarize(docs)
    print(render(summary))
    return 1 if args.strict and summary["violating"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
