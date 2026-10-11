"""TDD: v21 回測 CLI 必須能從專案根目錄直接執行。"""

import subprocess
import sys
from pathlib import Path


def test_v21_backtest_help_runs_without_pythonpath():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/backtest_integrated_v21.py", "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--slippage-bps" in result.stdout