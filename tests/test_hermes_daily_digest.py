"""TDD: Hermes 盤後摘要——自選清單解析、逾時與失敗要看得見、摘要檔不能寫一半。"""

import subprocess
from datetime import datetime

import pytest

from scripts import hermes_daily_digest as d

pytestmark = pytest.mark.unit


def test_watchlist_skips_comments_blanks_bad_codes_and_duplicates():
    text = "2330  # 台積電\n\n# 全行註解\n2317\n2330\nab\nbad code\n00878\n"
    assert d.read_watchlist(text) == ["2330", "2317", "00878"]


def test_watchlist_is_capped_and_empty_input_is_empty():
    assert len(d.read_watchlist("\n".join(f"{1000 + n}" for n in range(50)))) == d.MAX_SYMBOLS
    assert d.read_watchlist("") == [] and d.read_watchlist(None) == []


def test_a_shell_looking_line_is_never_a_symbol():
    assert d.read_watchlist("2330; rm -rf /\n$(id)\n`id`") == []


def test_question_names_the_symbol_and_forbids_advice():
    question = d.build_question("2330")
    assert question.startswith("2330 ") and "不要建議" in question and "張" in question and "中文名稱" in question


def fake_ask(answers):
    calls = []

    def ask(question):
        calls.append(question)
        return answers[len(calls) - 1]

    ask.calls = calls
    return ask


def test_collect_asks_in_order_and_keeps_errors_per_symbol():
    ask = fake_ask([("答一", ""), ("", "逾時（240 秒）")])
    results = d.collect(["2330", "2317"], ask)
    assert [r["symbol"] for r in results] == ["2330", "2317"]
    assert results[0] == {"symbol": "2330", "answer": "答一", "error": ""}
    assert results[1]["error"] == "逾時（240 秒）"
    assert "2330" in ask.calls[0] and "2317" in ask.calls[1]


def test_collect_marks_the_rest_as_not_run_when_the_time_budget_is_used_up():
    ticks = iter([0, 0, 100, 100, 100])
    results = d.collect(["2330", "2317", "2454"], fake_ask([("a", ""), ("b", "")]), budget=50, clock=lambda: next(ticks))
    assert [r["error"] for r in results] == ["", "未執行（超過時間預算）", "未執行（超過時間預算）"]


def test_render_counts_failures_and_flagged_answers_and_shows_each_symbol():
    results = [
        {"symbol": "2330", "answer": "估值偏高", "error": ""},
        {"symbol": "2317", "answer": "買超 ⚠️ 數字找不到出處", "error": ""},
        {"symbol": "2454", "answer": "", "error": "Hermes 沒有輸出"},
    ]
    text = d.render_digest("2026-10-13 23:00", results)
    assert "共 3 檔；失敗 1 檔；回答附提醒 1 檔" in text
    assert "## 2330\n\n估值偏高" in text and "## 2454\n\n【失敗】Hermes 沒有輸出" in text


def test_a_failed_symbol_with_a_flag_in_its_error_is_not_counted_as_flagged():
    results = [{"symbol": "2330", "answer": "", "error": "⚠️ 逾時"}]
    assert "失敗 1 檔；回答附提醒 0 檔" in d.render_digest("x", results)


def run_main(tmp_path, answers, watchlist="2330\n2317\n"):
    wl = tmp_path / "watchlist.txt"
    if watchlist is not None:
        wl.write_text(watchlist, encoding="utf-8")
    code = d.main(["--watchlist", str(wl), "--out-dir", str(tmp_path / "out")], ask=fake_ask(answers), now=lambda: datetime(2026, 10, 13, 23, 0))
    return code, tmp_path / "out" / "digest_20261013.md"


def test_main_writes_the_digest_named_by_date_and_returns_zero(tmp_path):
    code, path = run_main(tmp_path, [("甲", ""), ("乙", "")])
    assert code == 0 and "## 2317\n\n乙" in path.read_text(encoding="utf-8")
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_main_returns_one_but_still_writes_when_any_symbol_failed(tmp_path, capsys):
    code, path = run_main(tmp_path, [("甲", ""), ("", "逾時（240 秒）")])
    assert code == 1 and path.exists()
    assert "失敗 1 檔：2317" in capsys.readouterr().out


def test_main_refuses_a_missing_or_empty_watchlist_without_writing(tmp_path, capsys):
    code, path = run_main(tmp_path, [], watchlist=None)
    assert code == 2 and not path.exists() and "讀不到自選清單" in capsys.readouterr().err
    code, path = run_main(tmp_path, [], watchlist="# 只有註解\n")
    assert code == 2 and not path.exists() and "空的" in capsys.readouterr().err


def patch_run(monkeypatch, result=None, error=None):
    def run(command, **kwargs):
        if error:
            raise error
        return result

    monkeypatch.setattr(d.subprocess, "run", run)


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


def test_ask_hermes_returns_the_trimmed_answer(monkeypatch):
    patch_run(monkeypatch, completed("  答案\n"))
    assert d.ask_hermes("q") == ("答案", "")


@pytest.mark.parametrize(
    "result, error, expected",
    [
        (completed("", "boom", 3), None, "結束碼 3"),
        (completed("  \n"), None, "沒有輸出"),
        (None, subprocess.TimeoutExpired("hermes", 5), "逾時"),
        (None, FileNotFoundError("nope"), "無法執行"),
    ],
)
def test_ask_hermes_turns_every_failure_into_an_error_message(monkeypatch, result, error, expected):
    patch_run(monkeypatch, result, error)
    answer, message = d.ask_hermes("q", timeout=5)
    assert answer == "" and expected in message


def test_ask_hermes_runs_in_the_neutral_directory_without_a_shell(monkeypatch):
    seen = {}

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return completed("ok")

    monkeypatch.setattr(d.subprocess, "run", run)
    d.ask_hermes("2330 估值")
    assert seen["command"] == [str(d.HERMES), "-z", "2330 估值"]
    assert seen["cwd"] == d.WORKDIR and seen.get("shell") is not True
    assert str(d.HERMES.parent) in seen["env"]["PATH"] and seen["timeout"] == d.CALL_TIMEOUT
