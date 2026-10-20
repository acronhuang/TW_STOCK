"""TDD: 角色簡化影子測試——編制各自設定環境變數、續跑不重算、比較含 Wilson 區間與買進賣出對翻，且單檔失敗不中斷整批。"""

import json
import os
from datetime import datetime

import pytest

from scripts import rule_roles_shadow as shadow

pytestmark = pytest.mark.unit


def row(arm, symbol, final, votes=("持有", "持有", "持有"), wall=10.0, error=None):
    r = {"arm": arm, "symbol": symbol, "final": final, "votes": [("m", v) for v in votes], "wall": wall}
    if error:
        r["error"] = error
    return r


def test_wilson_interval_brackets_the_rate_and_is_wider_for_fewer_samples():
    low, high = shadow.wilson(44, 48)
    assert low < 44 / 48 < high
    assert shadow.wilson(4, 5)[1] - shadow.wilson(4, 5)[0] > high - low
    assert shadow.wilson(0, 0) is None
    assert shadow.wilson(5, 5)[1] == 1.0


def test_compare_counts_same_verdicts_buy_sell_flips_and_identical_votes_and_skips_missing_verdicts():
    rows = [row("P", "1", "買進"), row("F", "1", "賣出", ("賣出", "賣出", "持有")),
            row("P", "2", "持有"), row("F", "2", "持有"),
            row("P", "3", None), row("F", "3", "持有"),
            row("P", "4", "持有")]

    assert shadow.compare(shadow.by_arm(rows), "P", "F") == (1, 2, 1, 1)


def test_the_summary_shows_each_comparison_with_its_noise_floor_and_the_flip_count():
    rows = ([row("P", str(i), "持有") for i in range(10)] + [row("P2", str(i), "持有") for i in range(9)] + [row("P2", "9", "買進")]
            + [row("F", str(i), "持有") for i in range(8)] + [row("F", "8", "賣出"), row("F", "9", "買進")])

    text = shadow.summarize(rows, "2026-10-23")

    assert "| P↔P2 雜訊底線：同編制再跑一次 | 9/10 = 90%" in text
    assert "| P↔F 現行 vs 六角色全 LLM | 8/10 = 80%" in text and "V↔P" not in text
    assert "- P：持有10" in text and "每檔耗時中位數 10 秒" in text


def test_failures_are_listed_and_leave_nothing_to_compare():
    rows = [row("P", "1", "持有"), row("F", "1", None, error="TimeoutError: x")]

    text = shadow.summarize(rows, "2026-10-23")

    assert "失敗 1 筆" in text and "- F 1：TimeoutError: x" in text and "| 無可比檔 |" in text


def fake_result(final="持有"):
    return {"consensus": {"final": final, "votes": [{"model": "qwen3.8:27b", "vote": final}]}, "models": {"value-analyst": "x"},
            "reports": {"value-analyst": "嚴重高估（…）"}}


def test_each_arm_sets_its_own_environment_while_running_and_restores_it(tmp_path, monkeypatch):
    monkeypatch.setenv("TEAM_RULE_ROLES", "original")
    seen = {}

    def record(arm):
        def analyze(symbol, quick):
            seen[arm] = os.environ.get("TEAM_RULE_ROLES", "<unset>")
            return fake_result()
        return analyze

    for arm in ("P", "F", "V"):
        shadow.run_arm(arm, ["2330"], record(arm), tmp_path / "o.jsonl", set(), workers=1)

    assert seen == {"P": "<unset>", "F": "", "V": "risk-manager,chip-analyst,value-analyst"}
    assert os.environ["TEAM_RULE_ROLES"] == "original"
    assert all(not r.get("error") for r in shadow.load_rows(tmp_path / "o.jsonl"))


def test_the_environment_is_restored_even_when_a_stock_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)

    def boom(symbol, quick):
        raise RuntimeError("llm down")

    shadow.run_arm("V", ["2330", "2317"], boom, tmp_path / "o.jsonl", set(), workers=1)

    assert "TEAM_RULE_ROLES" not in os.environ
    rows = shadow.load_rows(tmp_path / "o.jsonl")
    assert [r["error"] for r in rows] == ["RuntimeError: llm down"] * 2 and all(r["final"] is None for r in rows)


def test_a_rerun_skips_finished_pairs_and_retries_failed_ones(tmp_path):
    out = tmp_path / "o.jsonl"
    calls = []

    def analyze(symbol, quick):
        calls.append(symbol)
        if symbol == "2317" and len(calls) == 2:
            raise RuntimeError("first time fails")
        return fake_result()

    shadow.run_arm("P", ["2330", "2317"], analyze, out, set(), workers=1)
    done = {(r["arm"], r["symbol"]) for r in shadow.load_rows(out) if not r.get("error")}
    shadow.run_arm("P", ["2330", "2317"], analyze, out, done, workers=1)

    assert calls == ["2330", "2317", "2317"]
    assert shadow.by_arm(shadow.load_rows(out))["P"]["2317"]["final"] == "持有"


def test_main_runs_every_arm_writes_the_dated_files_and_prints_the_report(tmp_path, capsys):
    code = shadow.main(["--symbols", "2330", "2317", "--workers", "1", "--out-dir", str(tmp_path)],
                       analyze=lambda s, quick: fake_result(), now=lambda: datetime(2026, 10, 23, 10, 30))

    assert code == 0
    rows = shadow.load_rows(tmp_path / "shadow_20261023.jsonl")
    assert sorted({r["arm"] for r in rows}) == ["F", "P", "P2", "V"] and len(rows) == 8
    assert "| V↔F 價值角色改模板 vs 六角色全 LLM | 2/2 = 100%" in (tmp_path / "report_20261023.md").read_text(encoding="utf-8")
    assert "== 編制 P：2 檔" in capsys.readouterr().out


def test_report_only_rewrites_the_report_without_running_anything(tmp_path):
    (tmp_path / "shadow_20261023.jsonl").write_text(json.dumps(row("P", "1", "持有")) + "\n", encoding="utf-8")

    def never(symbol, quick):
        raise AssertionError("must not run")

    shadow.main(["--report-only", "--out-dir", str(tmp_path)], analyze=never, now=lambda: datetime(2026, 10, 23))

    assert "共 1 檔" in (tmp_path / "report_20261023.md").read_text(encoding="utf-8")


def test_an_unknown_arm_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        shadow.main(["--symbols", "1", "--arms", "P,ZZ", "--out-dir", str(tmp_path)], analyze=lambda s, quick: fake_result())


def test_main_resumes_from_the_existing_file_retrying_failures_but_not_finished_pairs(tmp_path):
    out = tmp_path / "shadow_20261023.jsonl"
    out.write_text(json.dumps(row("P", "2330", None, error="TimeoutError: x")) + "\n" + json.dumps(row("P", "2317", "持有")) + "\n", encoding="utf-8")
    calls = []

    def analyze(symbol, quick):
        calls.append((os.environ.get("TEAM_RULE_ROLES"), symbol))
        return fake_result()

    shadow.main(["--symbols", "2330", "2317", "--arms", "P", "--workers", "1", "--out-dir", str(tmp_path)],
                analyze=analyze, now=lambda: datetime(2026, 10, 23))

    assert calls == [(None, "2330")]
