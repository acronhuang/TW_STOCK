"""CLI 查詢工具測試"""
from pathlib import Path

import pytest
import subprocess
import sys

# CWE-798: 以 repo 根目錄相對推導 cwd（跨 OS，不硬編碼 /home/mdsadmin）。
_REPO_ROOT = str(Path(__file__).resolve().parents[1])

# ADR-0011 分類（2026-08-16）：純 CLI 參數解析
pytestmark = pytest.mark.unit


class TestCLIQuery:
    def test_health_command(self):
        r = subprocess.run(
            [sys.executable, 'src/cli/query.py', 'health'],
            capture_output=True, text=True, timeout=30,
            cwd=_REPO_ROOT
        )
        assert r.returncode == 0
        assert 'ok' in r.stdout or 'stock_price' in r.stdout

    def test_factors_command(self):
        r = subprocess.run(
            [sys.executable, 'src/cli/query.py', 'factors', '2330'],
            capture_output=True, text=True, timeout=30,
            cwd=_REPO_ROOT
        )
        assert r.returncode == 0
        assert '2330' in r.stdout

    def test_no_args_shows_help(self):
        r = subprocess.run(
            [sys.executable, 'src/cli/query.py'],
            capture_output=True, text=True, timeout=10,
            cwd=_REPO_ROOT
        )
        assert r.returncode == 0
        assert 'twstock' in r.stdout.lower() or 'usage' in r.stdout.lower() or 'factors' in r.stdout.lower()

    def test_macro_command(self):
        r = subprocess.run(
            [sys.executable, 'src/cli/query.py', 'macro'],
            capture_output=True, text=True, timeout=30,
            cwd=_REPO_ROOT
        )
        assert r.returncode == 0
