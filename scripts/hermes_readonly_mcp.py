#!/usr/bin/env python3
"""Hermes Agent 的唯讀 MCP 伺服器（stdio）：只暴露三個查詢工具，全部走本機分析 API 的 GET 白名單。

只用標準函式庫。註冊：hermes mcp add twstock --command <python> --args <本檔>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ops import readonly_tools  # noqa: E402


def write(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    readonly_tools.serve(sys.stdin, write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
