"""TDD: 週五週跑不與收盤後管線同時搶 .28：管線還在跑就等，等不到就逾時照跑，可關閉。"""

import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "wait_for_pipeline.sh"


def run_wait(pattern, max_sec, poll=1):
    env = {**os.environ, "WEEKLY_PIPELINE_PATTERN": pattern, "WEEKLY_WAIT_PIPELINE_MAX_SEC": str(max_sec), "WEEKLY_WAIT_PIPELINE_POLL_SEC": str(poll)}
    start = time.time()
    result = subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    return result, time.time() - start


@pytest.fixture
def fake_pipeline():
    procs = []

    def start(seconds):
        name = f"fakepipeline_{uuid.uuid4().hex}"
        procs.append(subprocess.Popen(["bash", "-c", f"exec -a {name} sleep {seconds}"]))
        time.sleep(0.3)
        return name

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()


def test_it_returns_at_once_when_no_pipeline_is_running():
    result, elapsed = run_wait(f"nothing_{uuid.uuid4().hex}", 30)

    assert result.returncode == 0 and elapsed < 1.5 and "等" not in result.stdout


def test_it_waits_until_the_pipeline_finishes(fake_pipeline):
    name = fake_pipeline(3)

    result, elapsed = run_wait(name, 30)

    assert result.returncode == 0 and 1.5 <= elapsed < 10
    assert "仍在執行" in result.stdout and "已結束" in result.stdout


def test_it_gives_up_after_the_limit_and_lets_the_weekly_run_start(fake_pipeline):
    name = fake_pipeline(60)

    result, elapsed = run_wait(name, 2)

    assert result.returncode == 0 and 1.5 <= elapsed < 8
    assert "仍照常啟動" in result.stdout


def test_a_zero_limit_turns_the_waiting_off(fake_pipeline):
    name = fake_pipeline(60)

    result, elapsed = run_wait(name, 0)

    assert result.returncode == 0 and elapsed < 1.5 and result.stdout == ""


def test_the_default_pattern_matches_the_pipeline_entry_in_the_crontab_snapshot():
    default = re.search(r'PATTERN="\$\{WEEKLY_PIPELINE_PATTERN:-(.*?)\}"', SCRIPT.read_text(encoding="utf-8")).group(1)
    cron = (ROOT / "deploy" / "crontab.txt").read_text(encoding="utf-8")

    assert re.search(default, cron), "預設比對字串要能對到排程裡的 evening_pipeline.sh"


def test_the_weekly_run_waits_after_taking_its_lock_and_before_starting_phase_one():
    text = (ROOT / "scripts" / "weekly_team_full.sh").read_text(encoding="utf-8")

    assert text.index("flock -n 200") < text.index("bash scripts/wait_for_pipeline.sh") < text.index('echo "──── [1/4] phase1')
