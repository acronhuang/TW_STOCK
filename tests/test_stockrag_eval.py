"""TDD: RAG 查詢集評分與前視檢查（純函式，不需要 Ollama 或 MongoDB）。"""

from datetime import datetime

import pytest

from scripts import stockrag_eval as ev

pytestmark = pytest.mark.unit


def test_first_rank_is_one_based_over_the_returned_chunks_and_none_when_absent():
    assert ev.first_rank(["a.md"], ["x.md", "a.md", "a.md"]) == 2
    assert ev.first_rank(["a.md", "b.md"], ["b.md"]) == 1
    assert ev.first_rank(["a.md"], ["x.md", "y.md"]) is None


def test_summary_counts_recall_within_k_and_mean_reciprocal_rank():
    summary = ev.summarize([1, 3, None, 6], k=5)

    assert summary["recall"] == pytest.approx(2 / 4)
    assert summary["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 0) / 4)
    assert summary["queries"] == 4 and summary["misses"] == 2


def test_summary_of_nothing_is_zero_rather_than_a_division_error():
    assert ev.summarize([], k=5) == {"recall": 0.0, "mrr": 0.0, "queries": 0, "misses": 0}


def test_a_leak_is_any_hit_dated_after_the_cutoff_or_without_a_provable_date():
    cutoff = datetime(2026, 9, 20, 23, 59, 59)
    hits = [{"path": "ok.md", "doc_date": datetime(2026, 9, 1)},
            {"path": "late.md", "doc_date": datetime(2026, 9, 21)},
            {"path": "blank.md", "doc_date": None}]

    assert ev.leaks(hits, cutoff) == ["late.md", "blank.md"]


def test_gates_report_each_failed_condition_in_words():
    thresholds = {"recall": 0.8, "mrr": 0.5}

    assert ev.failed_gates({"recall": 0.9, "mrr": 0.6}, 0, 0, thresholds) == []
    failures = ev.failed_gates({"recall": 0.7, "mrr": 0.4}, 2, 1, thresholds)
    assert len(failures) == 4
    assert any("recall" in f for f in failures) and any("mrr" in f for f in failures)
    assert any("前視" in f for f in failures) and any("應被截止" in f for f in failures)
