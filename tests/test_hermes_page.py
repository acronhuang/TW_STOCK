"""TDD: Hermes 助理頁——問題以單一參數交給 hq、一次只處理一題、逾時與失敗都要說清楚。"""

import subprocess
from pathlib import Path

import pytest

from dashboard.pages import hermes_page as hp

pytestmark = pytest.mark.unit


class Done:
    def __init__(self, stdout="答案", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class Runner:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result or Done(), error, []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error:
            raise self.error
        return self.result


def test_the_question_is_one_argument_and_nothing_goes_through_a_shell():
    run = Runner()
    text, failed = hp.ask("  2330 的公平價; rm -rf / $(id) \n ", run=run, hq="/x/hq")

    argv, kwargs = run.calls[0]
    assert argv == ["/x/hq", "2330 的公平價; rm -rf / $(id)"] and "shell" not in kwargs
    assert kwargs["timeout"] == hp.TIMEOUT_SECONDS and kwargs["capture_output"] is True and kwargs["encoding"] == "utf-8"
    assert (text, failed) == ("答案", False)


def test_the_answer_is_trimmed():
    assert hp.ask("q", run=Runner(Done(stdout="\n  答案  \n")), hq="hq") == ("答案", False)


@pytest.mark.parametrize("question", ["", "   ", None])
def test_an_empty_question_is_refused_without_starting_anything(question):
    run = Runner()
    text, failed = hp.ask(question, run=run, hq="hq")

    assert failed and "請先輸入" in text and run.calls == []


def test_a_question_over_the_limit_is_refused_but_one_at_the_limit_is_accepted():
    run = Runner()
    assert hp.ask("字" * (hp.MAX_QUESTION + 1), run=run, hq="hq")[1] is True and run.calls == []
    assert hp.ask("字" * hp.MAX_QUESTION, run=run, hq="hq")[1] is False and len(run.calls) == 1


def test_only_one_question_is_handled_at_a_time():
    run = Runner()
    assert hp._busy.acquire(blocking=False)
    try:
        text, failed = hp.ask("q", run=run, hq="hq")
    finally:
        hp._busy.release()

    assert failed and "另一個問題" in text and run.calls == []


@pytest.mark.parametrize("runner", [
    Runner(Done()),
    Runner(error=subprocess.TimeoutExpired("hq", 1)),
    Runner(error=FileNotFoundError("hq")),
    Runner(Done(returncode=1)),
])
def test_the_lock_is_released_after_every_outcome(runner):
    hp.ask("q", run=runner, hq="hq")

    assert hp._busy.acquire(blocking=False)
    hp._busy.release()


def test_a_timeout_says_how_long_it_waited():
    text, failed = hp.ask("q", run=Runner(error=subprocess.TimeoutExpired("hq", 1)), hq="hq")

    assert failed and str(hp.TIMEOUT_SECONDS) in text


def test_a_missing_launcher_is_reported_not_raised():
    text, failed = hp.ask("q", run=Runner(error=FileNotFoundError("no hq")), hq="hq")

    assert failed and "無法啟動" in text and "no hq" in text


@pytest.mark.parametrize("done,expected", [
    (Done(stdout="", returncode=0), "助理沒有回答。"),
    (Done(stdout="部分", returncode=2), "助理沒有回答。"),
    (Done(stdout="", stderr="boom", returncode=1), "助理沒有回答：boom"),
])
def test_a_failed_or_silent_run_is_an_error_with_the_stderr_tail(done, expected):
    assert hp.ask("q", run=Runner(done), hq="hq") == (expected, True)


def test_only_the_tail_of_a_long_stderr_is_shown():
    text, _ = hp.ask("q", run=Runner(Done(stdout="", stderr="x" * 500 + "END", returncode=1)), hq="hq")

    assert text == "助理沒有回答：" + "x" * 197 + "END"


def test_the_launcher_is_found_on_the_path_or_under_the_home_directory(monkeypatch):
    monkeypatch.setattr(hp.shutil, "which", lambda name: "/opt/bin/hq")
    assert hp.hq_path() == "/opt/bin/hq"
    monkeypatch.setattr(hp.shutil, "which", lambda name: None)
    assert Path(hp.hq_path()) == Path.home() / ".local" / "bin" / "hq"


def test_the_page_has_no_hardcoded_absolute_path():
    source = (Path(hp.__file__)).read_text(encoding="utf-8")
    assert "/home/mdsadmin" not in source
