"""TDD: 新聞與重大訊息語料——可用時間、代號與日期欄位、決策截止時點與上線門檻。"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from scripts import stockrag_news as news
from scripts import stockrag_search as base

pytestmark = pytest.mark.unit


def major_row(**over):
    row = {"stock_id": "3432", "name": "台端", "date": datetime(2026, 10, 10), "time": "211554",
           "subject": "依臺灣證券交易所\r\n函辦理", "clause": "第51款", "detail": "1.事實發生日:115/10/10\n2.公司名稱:台端",
           "fact_date": datetime(2026, 10, 10)}
    row.update(over)
    return row


# ── 可用時間（發言時間才是公開時間，不是抓取時間）───────────────────────────
def test_an_announcement_becomes_available_at_its_statement_time():
    assert news.major_available_at(major_row()) == datetime(2026, 10, 10, 21, 15, 54)


def test_a_five_digit_time_is_zero_padded():
    assert news.major_available_at(major_row(time="70003")) == datetime(2026, 10, 10, 7, 0, 3)


def test_an_unreadable_time_falls_back_to_the_end_of_the_day_so_the_item_is_never_seen_too_early():
    assert news.major_available_at(major_row(time="")) == datetime(2026, 10, 10, 23, 59, 59)
    assert news.major_available_at(major_row(time="9x")) == datetime(2026, 10, 10, 23, 59, 59)


# ── 文件組裝 ───────────────────────────────────────────────────────────────
def test_an_announcement_document_carries_symbol_name_dates_and_readable_content():
    doc = news.major_doc(major_row())

    assert doc["symbol"] == "3432" and doc["name"] == "台端" and doc["kind"] == "announcement" and doc["source"] == "twse_major"
    assert doc["event_date"] == datetime(2026, 10, 10) and doc["doc_date"] == datetime(2026, 10, 10, 21, 15, 54)
    for part in ("台端", "3432", "2026-10-10 21:15", "依臺灣證券交易所 函辦理", "第51款", "事實發生日"):
        assert part in doc["content"]
    assert "\r" not in doc["content"] and doc["title"] == "依臺灣證券交易所 函辦理"


def test_content_is_capped_so_one_long_notice_cannot_dominate_cost_or_ranking():
    doc = news.major_doc(major_row(detail="長" * 5000))

    assert len(doc["content"]) <= news.MAX_CHARS


def test_rows_without_a_symbol_or_a_date_are_not_documents():
    assert news.major_doc(major_row(stock_id="")) is None
    assert news.major_doc(major_row(date=None)) is None


def test_the_key_is_stable_for_the_same_notice_and_differs_when_the_text_differs():
    assert news.major_doc(major_row())["key"] == news.major_doc(major_row())["key"]
    assert news.major_doc(major_row())["key"] != news.major_doc(major_row(subject="另一則"))["key"]


def test_a_media_snapshot_is_keyed_by_its_titles_so_an_unchanged_list_is_not_stored_twice():
    first = news.media_doc({"stock_id": "1101", "name": "台泥", "titles": ["甲", "乙"], "fetched_at": datetime(2026, 10, 9, 19, 31)})
    later = news.media_doc({"stock_id": "1101", "name": "台泥", "titles": ["甲", "乙"], "fetched_at": datetime(2026, 10, 11, 13, 58)})
    changed = news.media_doc({"stock_id": "1101", "name": "台泥", "titles": ["甲", "丙"], "fetched_at": datetime(2026, 10, 11, 13, 58)})

    assert first["key"] == later["key"] != changed["key"]
    assert first["doc_date"] == datetime(2026, 10, 9, 19, 31) and first["kind"] == "news" and first["symbol"] == "1101"
    assert "甲" in first["content"] and "台泥" in first["content"]


def test_a_media_snapshot_without_titles_is_skipped():
    assert news.media_doc({"stock_id": "1101", "titles": [], "fetched_at": datetime(2026, 10, 9)}) is None


# ── 檢索 ───────────────────────────────────────────────────────────────────
def hit_doc(key, symbol, when, kind="announcement", text="董事會決議 現金股利"):
    return {"key": key, "path": key, "chunk_idx": 0, "symbol": symbol, "name": symbol, "kind": kind, "title": key,
            "event_date": when and when.replace(hour=0, minute=0, second=0), "doc_date": when, "content": text}


@pytest.fixture
def corpus(monkeypatch):
    docs = [hit_doc("a-old", "2330", datetime(2026, 9, 1, 10)),
            hit_doc("a-new", "2330", datetime(2026, 10, 9, 10)),
            hit_doc("a-after", "2330", datetime(2026, 10, 12, 10)),
            hit_doc("b-new", "2454", datetime(2026, 10, 9, 10)),
            hit_doc("undated", "2330", None)]
    mat = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(docs), 1))
    monkeypatch.setattr(base, "embed", lambda text: [1.0, 0.0])
    return docs, mat


def keys(hits):
    return [h["key"] for h in hits]


def test_a_symbol_restricts_results_to_that_company(corpus):
    docs, mat = corpus

    assert set(keys(news.search("股利", docs, mat, k=10, symbols=["2454"]))) == {"b-new"}


def test_several_symbols_are_allowed(corpus):
    docs, mat = corpus

    assert set(keys(news.search("股利", docs, mat, k=10, symbols=["2330", "2454"], as_of=datetime(2026, 10, 10)))) == {"a-old", "a-new", "b-new"}


def test_nothing_after_the_decision_time_is_visible_and_undated_items_are_refused(corpus):
    docs, mat = corpus

    hits = news.search("股利", docs, mat, k=10, as_of=datetime(2026, 10, 10))

    assert "a-after" not in keys(hits) and "undated" not in keys(hits)


def test_an_item_published_one_second_after_the_decision_is_excluded_and_one_at_the_decision_is_kept(corpus):
    docs, mat = corpus
    docs[1]["doc_date"] = datetime(2026, 10, 9, 21, 15, 54)

    assert "a-new" in keys(news.search("股利", docs, mat, k=10, as_of=datetime(2026, 10, 9, 21, 15, 54)))
    assert "a-new" not in keys(news.search("股利", docs, mat, k=10, as_of=datetime(2026, 10, 9, 21, 15, 53)))


def test_the_window_keeps_only_recent_items_relative_to_the_cutoff(corpus):
    docs, mat = corpus

    hits = news.search("股利", docs, mat, k=10, as_of=datetime(2026, 10, 10), window_days=7)

    assert set(keys(hits)) == {"a-new", "b-new"}


def test_newer_items_win_a_tie_and_age_counts_from_the_cutoff_not_from_today(corpus):
    docs, mat = corpus
    cutoff = datetime(2026, 10, 10)

    hits = news.search("股利", docs, mat, k=10, symbols=["2330"], as_of=cutoff)

    assert keys(hits) == ["a-new", "a-old"]
    assert hits[0]["age_days"] == (cutoff - datetime(2026, 10, 9, 10)).days


def test_without_a_cutoff_future_items_are_not_hidden_but_undated_ones_still_work(corpus):
    docs, mat = corpus

    assert "a-after" in keys(news.search("股利", docs, mat, k=10))


# ── 題目中的日期 ───────────────────────────────────────────────────────────
REF = datetime(2026, 10, 11, 12, 0)


@pytest.mark.parametrize("question, expected", [
    ("敦泰 7/20 公告的除息基準日", [datetime(2026, 7, 20)]),
    ("富邦金 10/6 取得債券", [datetime(2026, 10, 6)]),
    ("2026-09-23 可成買回股份", [datetime(2026, 9, 23)]),
    ("2026/9/2 友達", [datetime(2026, 9, 2)]),
    ("9月23日 的公告與 9/24", [datetime(2026, 9, 23), datetime(2026, 9, 24)]),
    ("12/25 那天", [datetime(2025, 12, 25)]),            # 晚於參考時點的月日視為去年
    ("9 月份自結盈餘與 13/45", []),                       # 只有月沒有日、無效月日都不算
    ("最近有什麼公告", []),
])
def test_dates_in_the_question_are_found_relative_to_the_reference_time(question, expected):
    assert news.extract_dates(question, REF) == expected


def test_a_date_in_the_question_outranks_recency_and_switches_decay_off(corpus):
    docs, mat = corpus      # a-old 2026-09-01、a-new 2026-10-09（其餘同分）

    hits = news.search("2330 9/1 股利", docs, mat, k=2, symbols=["2330"], as_of=datetime(2026, 10, 10))

    assert keys(hits)[0] == "a-old"


def test_without_a_date_the_newer_item_still_wins(corpus):
    docs, mat = corpus

    hits = news.search("2330 股利", docs, mat, k=2, symbols=["2330"], as_of=datetime(2026, 10, 10))

    assert keys(hits)[0] == "a-new"      # 兩筆分數相同時，較新者在前


@pytest.mark.parametrize("question, expected", [
    ("台端最近有什麼公告", True), ("近期重大訊息", True), ("最新消息", True), ("今天有什麼訊息", True),
    ("敦泰除息基準日的公告", False), ("中鋼 6 月份自結營收", False),
])
def test_recency_intent_is_recognised_from_the_wording(question, expected):
    assert news.wants_recent(question) is expected


@pytest.fixture
def graded(monkeypatch):
    """舊的那筆語意較符（向量、字面都第一），新的那筆較不相關。"""
    docs = [hit_doc("old-relevant", "2330", datetime(2026, 7, 20, 10), text="董事會決議 現金股利"),
            hit_doc("new-unrelated", "2330", datetime(2026, 10, 9, 10), text="媒體報導 股價走勢")]
    mat = np.array([[1.0, 0.0], [0.6, 0.8]], dtype=np.float32)
    monkeypatch.setattr(base, "embed", lambda text: [1.0, 0.0])
    return docs, mat


def test_without_recency_wording_the_more_relevant_old_item_wins(graded):
    docs, mat = graded

    hits = news.search("2330 現金股利", docs, mat, k=2, as_of=datetime(2026, 10, 10))

    assert keys(hits)[0] == "old-relevant"


def test_with_recency_wording_the_newer_item_is_preferred(graded):
    docs, mat = graded

    hits = news.search("2330 最近的現金股利", docs, mat, k=2, as_of=datetime(2026, 10, 10))

    assert keys(hits)[0] == "new-unrelated"


# ── 代號辨識 ───────────────────────────────────────────────────────────────
KNOWN = {"2330": "台積電", "3432": "台端", "2454": "聯發科"}


def test_symbols_are_found_by_code_and_by_name_and_a_year_is_not_mistaken_for_a_code():
    assert news.extract_symbols("2026 年 2330 最近有什麼公告？聯發科呢", KNOWN) == ["2330", "2454"]


def test_unknown_codes_and_short_fragments_are_ignored():
    assert news.extract_symbols("9999 和 台 怎麼樣", KNOWN) == []


def test_market_suffixes_are_not_required_when_a_user_types_a_company_name():
    known = {"6919": "康霈*", "8487": "愛爾達-創", "6415": "矽力*-KY"}

    assert news.extract_symbols("康霈 新藥、愛爾達、矽力怎麼樣", known) == ["6919", "8487", "6415"]


# ── 決策截止時點 ───────────────────────────────────────────────────────────
def test_the_decision_cutoff_is_when_the_verdicts_were_created():
    docs = [{"created_at": datetime(2026, 10, 10, 5, 55)}, {"created_at": datetime(2026, 10, 10, 6, 10)}, {}]

    assert news.decision_cutoff(docs, datetime(2026, 10, 9)) == datetime(2026, 10, 10, 6, 10)


def test_without_creation_times_the_cutoff_is_the_end_of_the_decision_date():
    assert news.decision_cutoff([{}], datetime(2026, 10, 9)) == datetime(2026, 10, 9, 23, 59, 59)


# ── 上線門檻 ───────────────────────────────────────────────────────────────
def test_the_gate_opens_only_for_a_recent_passing_result(tmp_path):
    path = tmp_path / "gate.json"
    now = datetime(2026, 10, 12, 12, 0)

    assert news.gate_open(path, now) is False                       # 沒有紀錄
    news.write_gate(path, {"recall": 0.9, "mrr": 0.7}, passed=True, k=5, now=now)
    assert news.gate_open(path, now + timedelta(days=3)) is True
    assert news.gate_open(path, now + timedelta(days=30)) is False  # 過期要重測
    news.write_gate(path, {"recall": 0.5, "mrr": 0.2}, passed=False, k=5, now=now)
    assert news.gate_open(path, now) is False


def test_a_corrupt_gate_file_keeps_the_gate_closed(tmp_path):
    path = tmp_path / "gate.json"
    path.write_text("{not json", encoding="utf-8")

    assert news.gate_open(path, datetime(2026, 10, 12)) is False
