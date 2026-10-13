"""mops_major_sync 只要有一天的清單失敗就以非零狀態結束，排程才看得到失敗。"""

from unittest.mock import MagicMock

import pytest

from scripts import mops_major_sync as sync

pytestmark = pytest.mark.unit


def stats(day):
    return {"day": f"{day:%Y-%m-%d}", "markets": {"sii": {"official": 1, "held": 1}},
            "missing": 0, "filled": 0, "failed": 0, "applied": False}


def run_main(monkeypatch, run_day):
    monkeypatch.setattr(sync, "get_db", lambda: MagicMock())
    monkeypatch.setattr(sync, "Mops", lambda pause: object())
    monkeypatch.setattr(sync, "run_day", run_day)
    return sync.main(["--days", "2"])


def test_a_failed_day_list_makes_the_exit_code_nonzero_but_the_other_days_still_run(monkeypatch, capsys):
    seen = []

    def run_day(db, mops, day, markets, apply):
        seen.append(day)
        if len(seen) == 1:
            raise RuntimeError("清單回應異常")
        return stats(day)

    assert run_main(monkeypatch, run_day) == 1
    assert len(seen) == 2 and "清單失敗 1 天" in capsys.readouterr().out


def test_when_every_day_succeeds_the_exit_code_is_zero(monkeypatch, capsys):
    assert run_main(monkeypatch, lambda db, mops, day, markets, apply: stats(day)) == 0
    assert "清單失敗 0 天" in capsys.readouterr().out
