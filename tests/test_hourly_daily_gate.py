"""TDD: 每小時下載的「每日一次」閘門——基本面一天一輪、成功才記帳、失敗下一小時再試、閘門壞掉不停下載。"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from scripts import hourly_daily_gate as gate_cli
from src.ops import daily_gate

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
CATS = ("基本面",)
NOON = datetime(2026, 10, 21, 12, 5)


def test_settings_default_to_fundamentals_after_three_and_read_the_environment():
    assert daily_gate.settings({}) == (("基本面",), 3)
    assert daily_gate.settings({"HOURLY_DAILY_CATEGORIES": "基本面, 籌碼面", "HOURLY_DAILY_HOUR": "5"}) == (("基本面", "籌碼面"), 5)
    assert daily_gate.settings({"HOURLY_DAILY_CATEGORIES": ""}) == ((), 3)
    assert daily_gate.settings({"HOURLY_DAILY_HOUR": "abc"})[1] == 3


def test_a_category_that_is_not_daily_is_always_due():
    assert daily_gate.is_due("技術面", NOON, {"技術面": "2026-10-21"}, CATS, 3)


def test_a_daily_category_waits_for_its_hour_then_runs_once_per_day():
    assert not daily_gate.is_due("基本面", datetime(2026, 10, 21, 2, 5), {}, CATS, 3)
    assert daily_gate.is_due("基本面", datetime(2026, 10, 21, 3, 5), {}, CATS, 3)
    assert not daily_gate.is_due("基本面", NOON, {"基本面": "2026-10-21"}, CATS, 3)
    assert daily_gate.is_due("基本面", datetime(2026, 10, 22, 3, 5), {"基本面": "2026-10-21"}, CATS, 3)


def test_marking_records_only_daily_categories_and_leaves_no_temp_file(tmp_path):
    state = tmp_path / "state.json"

    daily_gate.mark_done(state, "技術面", NOON, CATS)
    assert not state.exists()
    daily_gate.mark_done(state, "基本面", NOON, CATS)

    assert json.loads(state.read_text(encoding="utf-8")) == {"基本面": "2026-10-21"}
    assert not Path(f"{state}.tmp").exists()


def test_a_broken_or_foreign_state_file_reads_as_empty(tmp_path):
    for content in ("{not json", "[1, 2]", ""):
        (tmp_path / "s.json").write_text(content, encoding="utf-8")
        assert daily_gate.load(tmp_path / "s.json") == {}
    assert daily_gate.load(tmp_path / "missing.json") == {}


def run_cli(argv, monkeypatch, now=NOON, **env):
    for key in ("HOURLY_DAILY_CATEGORIES", "HOURLY_DAILY_HOUR"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return gate_cli.main(["gate", *argv], now=lambda: now)


def test_the_command_says_run_with_0_and_not_due_with_10_and_done_makes_it_not_due(tmp_path, monkeypatch):
    state = str(tmp_path / "s.json")

    assert run_cli(["check", "基本面", state], monkeypatch) == 0
    assert run_cli(["done", "基本面", state], monkeypatch) == 0
    assert run_cli(["check", "基本面", state], monkeypatch) == gate_cli.NOT_DUE == 10
    assert run_cli(["check", "技術面", state], monkeypatch) == 0
    assert run_cli(["check", "基本面", state], monkeypatch, now=datetime(2026, 10, 22, 4, 0)) == 0


def test_the_command_fails_open_on_errors_and_rejects_unknown_actions(tmp_path, monkeypatch, capsys):
    assert run_cli(["check"], monkeypatch) == 0                      # 少參數
    assert "daily gate error" in capsys.readouterr().err
    assert run_cli(["frobnicate", "基本面", str(tmp_path / "s.json")], monkeypatch) == 2


# ── 端到端：在暫存專案裡真的跑 hourly_data_update.sh，下載器換成記錄用的替身 ───────────────────

STUB_DOWNLOADER = """import os, sys
category = sys.argv[sys.argv.index("--categories") + 1]
with open(os.environ["DL_CALLS"], "a", encoding="utf-8") as f:
    f.write(category + "\\n")
sys.exit(1 if category in os.environ.get("DL_FAIL", "").split(",") else 0)
"""


@pytest.fixture
def sandbox(tmp_path):
    project = tmp_path / "proj"
    for sub in ("scripts", "src/ops", "src/downloaders", "bin"):
        (project / sub).mkdir(parents=True)
    for name in ("hourly_data_update.sh", "hourly_daily_gate.py", "hourly_alert_gate.py"):
        shutil.copy(ROOT / "scripts" / name, project / "scripts" / name)
    for name in ("alert_throttle.py", "daily_gate.py"):
        shutil.copy(ROOT / "src/ops" / name, project / "src/ops" / name)
    for pkg in ("src", "src/ops"):
        (project / pkg / "__init__.py").write_text("", encoding="utf-8")
    (project / "src/downloaders/unified_downloader.py").write_text(STUB_DOWNLOADER, encoding="utf-8")
    (project / "scripts/log_finmind_usage.py").write_text('print("FinMind 伺服器端用量 0/600")\n', encoding="utf-8")
    (project / "scripts/notify_failure.sh").write_text("exit 0\n", encoding="utf-8")
    (project / ".env").write_text("FINMIND_API_TOKEN=x\n", encoding="utf-8")
    for name, body in (("mongosh", "echo 1"), ("sleep", "exit 0")):
        stub = project / "bin" / name
        stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        stub.chmod(0o755)

    def run(**env):
        calls = project / "calls.txt"
        calls.unlink(missing_ok=True)
        full = {**os.environ, "PATH": f"{project / 'bin'}:{os.environ['PATH']}", "DL_CALLS": str(calls), **env}
        for key in ("HOURLY_DAILY_CATEGORIES", "HOURLY_DAILY_HOUR"):
            if key not in env:
                full.pop(key, None)
        done = subprocess.run(["bash", str(project / "scripts/hourly_data_update.sh")], cwd=project, env=full, capture_output=True, text=True, timeout=120)
        return done.returncode, (calls.read_text(encoding="utf-8").split() if calls.exists() else [])

    run.project = project
    return run


OTHERS = ["技術面", "籌碼面", "衍生性商品", "其他"]


def test_the_hourly_script_downloads_fundamentals_once_a_day_and_the_other_categories_every_hour(sandbox):
    first = sandbox(HOURLY_DAILY_HOUR="0")
    second = sandbox(HOURLY_DAILY_HOUR="0")

    assert first == (0, ["技術面", "基本面", "籌碼面", "衍生性商品", "其他"])
    assert second == (0, OTHERS)


def test_before_its_hour_the_daily_category_is_skipped(sandbox):
    assert sandbox(HOURLY_DAILY_HOUR="24") == (0, OTHERS)


def test_emptying_the_daily_list_restores_hourly_fundamentals(sandbox):
    for _ in range(2):
        assert sandbox(HOURLY_DAILY_CATEGORIES="", HOURLY_DAILY_HOUR="0") == (0, ["技術面", "基本面", "籌碼面", "衍生性商品", "其他"])


def test_a_failed_daily_download_is_not_recorded_so_the_next_hour_retries(sandbox):
    failed = sandbox(HOURLY_DAILY_HOUR="0", DL_FAIL="基本面")
    retried = sandbox(HOURLY_DAILY_HOUR="0")
    done = sandbox(HOURLY_DAILY_HOUR="0")

    assert failed[0] == 1 and "基本面" in failed[1]
    assert retried == (0, ["技術面", "基本面", "籌碼面", "衍生性商品", "其他"])
    assert done == (0, OTHERS)


def test_a_broken_gate_never_stops_the_downloads(sandbox):
    (sandbox.project / "scripts/hourly_daily_gate.py").write_text("raise SystemExit(1)\n", encoding="utf-8")

    for _ in range(2):
        assert sandbox(HOURLY_DAILY_HOUR="0") == (0, ["技術面", "基本面", "籌碼面", "衍生性商品", "其他"])


def test_a_skipped_category_still_counts_as_a_successful_round(sandbox):
    sandbox(HOURLY_DAILY_HOUR="0")
    sandbox(HOURLY_DAILY_HOUR="0")

    summaries = sorted((sandbox.project / "logs/hourly_updates").glob("daily_summary_*.log"))
    assert "成功: 5 個類別" in summaries[-1].read_text(encoding="utf-8").split("更新總結")[-1]
