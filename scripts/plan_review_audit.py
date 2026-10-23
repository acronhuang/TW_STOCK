#!/usr/bin/env python3
"""彙整 Hermes 計畫審查的觸發紀錄（logs/hermes_plan_review.jsonl），供人工檢查誤判與漏判。唯讀。

plan＝實際走了計畫審查；near_miss＝有買賣動詞與審查詞但缺止損或張數細節，沒有走審查。
用法：python scripts/plan_review_audit.py [--file 路徑] [--limit 20]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "logs" / "hermes_plan_review.jsonl"


def load(path):
    """回 (紀錄清單, 壞行數)。"""
    records, bad = [], 0
    if not Path(path).exists():
        return records, bad
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            bad += 1
            continue
        records.append(item) if isinstance(item, dict) else None
    return records, bad


def summarize(records, bad=0, limit=20):
    kinds = Counter(r.get("kind") for r in records)
    verdicts = Counter((r.get("verdict") or "（無結論）") for r in records if r.get("kind") == "plan")
    lines = [f"紀錄 {len(records)} 筆（壞行 {bad}）：走計畫審查 {kinds.get('plan', 0)}、差一點沒走 {kinds.get('near_miss', 0)}"]
    if verdicts:
        lines.append("計畫審查結論分布：" + "、".join(f"{v} {n}" for v, n in verdicts.most_common()))
    for kind, title in (("plan", "最近的計畫審查（確認抽出的數字與問題相符）"), ("near_miss", "最近差一點沒走的問題（確認是否漏判）")):
        rows = [r for r in records if r.get("kind") == kind][-limit:]
        if rows:
            lines.append(f"\n## {title}")
            for r in rows:
                extra = f"  抽出：{json.dumps(r.get('args'), ensure_ascii=False)}  {r.get('verdict') or ''}" if kind == "plan" else ""
                lines.append(f"- {r.get('at', '')} {r.get('question', '')}{extra}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=DEFAULT)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    records, bad = load(args.file)
    print(summarize(records, bad, args.limit) if records or bad else "還沒有紀錄。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
