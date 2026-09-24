#!/usr/bin/env python3
"""CI 護欄:每個測試都必須標 tier marker(unit / needs_data / prod_data)。

為什麼(2026-09-25):無 tier 的測試會漏出分層策略 —— 既不進免-DB 的 unit-gate
(純邏輯秒級回歸安全網),也拿不到 needs_data 的『無種子自動 skip』護欄,於是在
dev 本機無 mongo 時炸紅、或純邏輯回歸被淹沒在 Mongo timeout 裡。這輪把 11 個漏網
測試全數歸位後,用本護欄鎖住成果,防止未來新增測試又漏標。

以 pytest 自身的 marker 解析(含 module / class / function 三層)判定,
避免 AST 靜態解析誤判 pytestmark 繼承。無 tier → 印出清單並以 exit 1 擋下。

用法:python scripts/check_tier_markers.py
"""
from __future__ import annotations

import subprocess
import sys

TIER_MARKERS = ("unit", "needs_data", "prod_data")


def main() -> int:
    expr = " and ".join(f"not {m}" for m in TIER_MARKERS)
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--collect-only", "-q",
            "-o", "addopts=",            # 清掉 pytest.ini 的 -v(否則輸出樹狀難解析)
            "-p", "no:cacheprovider",
            "-m", expr,
        ],
        capture_output=True, text=True,
    )
    # 只有 pytest 內部錯誤(usage error=4)才視為失敗;
    # exit 5(no tests collected)正是『全部都有 tier』的成功情形。
    if proc.returncode == 4:
        sys.stderr.write(proc.stdout + proc.stderr)
        return 4

    offenders = [ln.strip() for ln in proc.stdout.splitlines() if "::" in ln]
    if offenders:
        print("❌ 以下測試缺少 tier marker(unit / needs_data / prod_data):")
        for node in offenders:
            print(f"   - {node}")
        print(
            f"\n共 {len(offenders)} 個。請依『資料相依程度』擇一標記:\n"
            "  · 純邏輯免 DB → @pytest.mark.unit\n"
            "  · 合成種子可驗 → @pytest.mark.needs_data\n"
            "  · 真實世界事實/深資料 → @pytest.mark.prod_data\n"
            "詳見 tests/README.md。"
        )
        return 1

    print("✅ 所有測試皆已標 tier marker(unit / needs_data / prod_data)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
