"""TDD: 決策問答把決策時點傳給所有檢索，且答案中找不到出處的數字會被標出來。"""

from datetime import datetime

import pytest

pytest.importorskip("streamlit")

from dashboard.pages import decision_qa as qa  # noqa: E402

pytestmark = pytest.mark.unit

CREATED = datetime(2026, 10, 10, 6, 10)
DOCS = [{"symbol": "2375", "name": "凱美", "final_verdict": "賣出", "created_at": datetime(2026, 10, 10, 5, 55)},
        {"symbol": "2330", "name": "台積電", "final_verdict": "買進", "created_at": CREATED}]


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self.text}


@pytest.fixture
def wired(monkeypatch):
    seen = {"prompt": None}
    monkeypatch.setattr(qa, "_db", lambda: object())
    monkeypatch.setattr(qa, "stock_snapshot", lambda db, code: f"{code} 收盤2425.0")
    monkeypatch.setattr(qa, "news_hits", lambda question, cutoff, k=5: (seen.setdefault("news_cutoff", cutoff) and ["[重大訊息 10/09 21:15 台端(3432)] 公告"], ""))
    monkeypatch.setattr(qa, "rag_hits", lambda question, k=4, as_of=None: seen.setdefault("rag_as_of", as_of) and ["[文件](2026-09-01) 內容"])

    def post(url, json=None, timeout=None):
        seen["prompt"] = json["prompt"]
        return FakeResponse(seen["answer"])

    monkeypatch.setattr(qa.requests, "post", post)
    return seen


def test_every_retrieval_is_cut_at_the_time_the_verdicts_were_created(wired):
    wired["answer"] = "資料庫中沒有相關內容。"

    qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    assert wired["news_cutoff"] == CREATED and wired["rag_as_of"] == CREATED


def test_the_prompt_carries_the_cutoff_the_news_block_and_the_no_arithmetic_rule(wired):
    wired["answer"] = "x"

    qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    prompt = wired["prompt"]
    assert "2026-10-10 06:10" in prompt and "台端(3432)" in prompt and "不得自行計算" in prompt


def test_numbers_without_a_source_are_listed_after_the_answer(wired):
    wired["answer"] = "收盤 2425.0，目標價 3,000 元。"

    answer, _ = qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    assert answer.startswith("收盤 2425.0") and "找不到出處" in answer and answer.rstrip().endswith("3000")


def test_a_fully_sourced_answer_is_returned_untouched(wired):
    wired["answer"] = "收盤 2425.0，2330 為買進。"

    answer, _ = qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    assert answer == "收盤 2425.0，2330 為買進。"


def test_a_closed_gate_gives_no_news_and_says_so_with_the_way_to_reopen_it(tmp_path, monkeypatch):
    gate = tmp_path / "gate.json"
    gate.write_text('{"passed": false, "k": 5, "recall": 0.5, "mrr": 0.2, "checked_at": "2026-10-12T21:00:00"}', encoding="utf-8")
    monkeypatch.setattr(qa, "NEWS_GATE", gate)

    hits, note = qa.news_hits("2330 好嗎", CREATED)

    assert hits == [] and "新聞檢索未啟用" in note and "stockrag_news_eval.py" in note


def test_the_context_names_the_closed_gate_instead_of_quoting_news(wired, monkeypatch):
    monkeypatch.setattr(qa, "news_hits", lambda question, cutoff, k=5: ([], "新聞檢索未啟用：上線門檻未通過或已過期"))
    wired["answer"] = "x"

    _, context = qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    assert "【新聞檢索】新聞檢索未啟用" in context and "【新聞與重大訊息" not in context

def test_a_closed_gate_gives_no_news_and_says_so_with_the_way_to_reopen_it(tmp_path, monkeypatch):
    gate = tmp_path / "gate.json"
    gate.write_text('{"passed": false, "k": 5, "recall": 0.5, "mrr": 0.2, "checked_at": "2026-10-12T21:00:00"}', encoding="utf-8")
    monkeypatch.setattr(qa, "NEWS_GATE", gate)

    hits, note = qa.news_hits("2330 好嗎", CREATED)

    assert hits == [] and "新聞檢索未啟用" in note and "stockrag_news_eval.py" in note


def test_the_context_names_the_closed_gate_instead_of_quoting_news(wired, monkeypatch):
    monkeypatch.setattr(qa, "news_hits", lambda question, cutoff, k=5: ([], "新聞檢索未啟用：上線門檻未通過或已過期"))
    wired["answer"] = "x"

    _, context = qa.answer_question("2330 好嗎", DOCS, datetime(2026, 10, 9))

    assert "【新聞檢索】新聞檢索未啟用" in context and "【新聞與重大訊息" not in context
