"""TDD: 計畫審查觸發紀錄的彙整腳本——壞行不崩、空檔明說、列出該人工檢查的問題。"""

import json

import pytest

from scripts import plan_review_audit as audit

pytestmark = pytest.mark.unit


def write(path, rows, extra=""):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n" + extra, encoding="utf-8")


ROWS = [
    {"at": "2026-10-23T10:00:00", "kind": "plan", "question": "我打算買 3 張 2330，停損 2300", "args": {"symbol": "2330", "stop": 2300.0}, "verdict": "結論：不通過"},
    {"at": "2026-10-23T10:05:00", "kind": "near_miss", "question": "我打算買 2330，合理嗎", "args": None, "verdict": None},
    {"at": "2026-10-23T10:06:00", "kind": "plan", "question": "準備賣 1 張 2317，停損 5%", "args": {"symbol": "2317"}, "verdict": "結論：通過"},
]


def test_summary_counts_kinds_verdicts_and_lists_questions_to_check(tmp_path):
    write(tmp_path / "a.jsonl", ROWS)
    records, bad = audit.load(tmp_path / "a.jsonl")
    text = audit.summarize(records, bad)
    assert "紀錄 3 筆（壞行 0）：走計畫審查 2、差一點沒走 1" in text
    assert "結論：不通過 1" in text and "結論：通過 1" in text
    assert "我打算買 2330，合理嗎" in text and '"stop": 2300.0' in text


def test_bad_lines_are_counted_not_fatal(tmp_path):
    write(tmp_path / "a.jsonl", ROWS[:1], extra="not json\n[1,2]\n")
    records, bad = audit.load(tmp_path / "a.jsonl")
    assert len(records) == 1 and bad == 1


def test_limit_keeps_only_the_most_recent(tmp_path):
    rows = [{"at": f"t{i}", "kind": "plan", "question": f"問題{i}", "args": {}, "verdict": "結論：通過"} for i in range(5)]
    write(tmp_path / "a.jsonl", rows)
    records, bad = audit.load(tmp_path / "a.jsonl")
    text = audit.summarize(records, bad, limit=2)
    assert "問題4" in text and "問題3" in text and "問題2" not in text


def test_missing_file_means_no_records_and_the_cli_says_so(tmp_path, monkeypatch, capsys):
    assert audit.load(tmp_path / "none.jsonl") == ([], 0)
    monkeypatch.setattr("sys.argv", ["plan_review_audit.py", "--file", str(tmp_path / "none.jsonl")])
    assert audit.main() == 0 and "還沒有紀錄" in capsys.readouterr().out
