#!/usr/bin/env python3
"""印出一行 FinMind 伺服器端用量，給每小時下載腳本寫進日誌。

用法：python scripts/log_finmind_usage.py <階段>
token 取自環境變數 FINMIND_API_TOKEN；查不到時印「無資料」，永遠以 0 結束，不影響下載流程。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ops import finmind_usage  # noqa: E402


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    phase = argv[0] if argv else ""
    usage = finmind_usage.fetch_usage(os.environ.get("FINMIND_API_TOKEN", ""))
    suffix = f"（{phase}）" if phase else ""
    print(f"FinMind {finmind_usage.describe(usage)}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
