"""備份健康檢查測試 —— 偵測備份過期/缺失（靜默失敗）。"""
import time
from pathlib import Path

import pytest

from src.monitoring.backup_health import check_backup_freshness


@pytest.mark.unit
def test_fresh_backup_passes(tmp_path):
    f = tmp_path / "tw_stock_analysis_20260922_010000.tar.gz"
    f.write_text("x")
    r = check_backup_freshness(str(tmp_path), max_age_hours=48)
    assert r["ok"] is True
    assert r["latest"] is not None
    assert r["age_hours"] is not None


@pytest.mark.unit
def test_stale_backup_flagged(tmp_path):
    f = tmp_path / "tw_stock_analysis_old.tar.gz"
    f.write_text("x")
    old = time.time() - 3 * 24 * 3600  # 3 天前
    import os
    os.utime(f, (old, old))
    r = check_backup_freshness(str(tmp_path), max_age_hours=48)
    assert r["ok"] is False
    assert r["age_hours"] > 48


@pytest.mark.unit
def test_no_backup_flagged(tmp_path):
    r = check_backup_freshness(str(tmp_path), max_age_hours=48)
    assert r["ok"] is False
    assert r["latest"] is None


@pytest.mark.unit
def test_missing_dir_flagged():
    r = check_backup_freshness("/nonexistent/path/xyz", max_age_hours=48)
    assert r["ok"] is False
    assert r["latest"] is None
