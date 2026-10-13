#!/usr/bin/env python3
"""防篡改指紋鏈：登記新文件並寫鏈頭備份，或核對帳本有沒有被繞過程式改動。

用法：
  python scripts/audit_chain.py register            登記 research_signal_snapshots、portfolio_trades 的新文件，更新鏈頭備份
  python scripts/audit_chain.py verify [--alert]    核對；有問題以非零狀態結束，--alert 另寫 schedule_alerts
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_db  # noqa: E402
from src.ops import audit_chain as chain  # noqa: E402

HEAD_FILE = ROOT / "logs" / "audit_chain_head.json"


def run_register(db) -> int:
    for collection in chain.LEDGERS:
        print(f"{collection}: 新登記 {chain.register(db, collection)} 筆")
    head = chain.write_head(db, HEAD_FILE)
    print(f"鏈頭 seq={head['seq']} hash={head['hash'][:16]}…" if head else "鏈是空的")
    return 0


def run_verify(db, alert: bool) -> int:
    result = chain.verify(db, head_file=HEAD_FILE)
    print(f"鏈 {result['entries']} 筆；" + ("通過" if result["ok"] else "未通過"))
    lines = []
    for label, key in (("鏈斷裂", "broken_links"), ("文件被改", "modified"), ("文件被刪", "missing"), ("鏈頭不符", "anchor")):
        if result[key]:
            lines.append(f"{label} {len(result[key])} 項：{'；'.join(result[key][:3])}")
    for line in lines:
        print("  ✗ " + line)
    if result["ok"]:
        return 0
    if alert:
        from src.ops.alert_dedup import insert_once
        insert_once(db["schedule_alerts"], {"ts": datetime.now(), "level": "critical", "source": "audit_chain",
                                            "message": "防篡改指紋鏈核對未通過：" + " / ".join(lines), "resolved": False})
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register", "verify"))
    parser.add_argument("--alert", action="store_true")
    args = parser.parse_args(argv)
    db = get_db()
    return run_register(db) if args.action == "register" else run_verify(db, args.alert)


if __name__ == "__main__":
    raise SystemExit(main())
