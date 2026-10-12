"""TDD: 蔡森全市場掃描必須能從任何目錄直接執行（晚間管線以 `python scripts/senvision_market_scan.py` 呼叫）。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.mark.parametrize("name", ["senvision_market_scan.py", "senvision_chart.py"])
def test_the_script_imports_without_the_project_root_being_pre_set_on_the_path(tmp_path, name):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    result = subprocess.run([sys.executable, str(SCRIPTS / name), "--help"], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=120)

    assert "No module named" not in result.stderr, result.stderr[-400:]
    assert result.returncode == 0, result.stderr[-400:]
