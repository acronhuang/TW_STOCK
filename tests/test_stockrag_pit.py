"""TDD: RAG 檢索的前視防護（as_of）——決策時點之後才出現的文件，任何情況都不得進入結果。"""

from datetime import datetime

import numpy as np
import pytest

from scripts import stockrag_search as rag

pytestmark = pytest.mark.unit

CUTOFF = datetime(2026, 9, 20, 23, 59, 59)


def doc(path, when, text="資料完整度 診斷", kind="doc"):
    return {"path": path, "chunk_idx": 0, "title": path, "kind": kind, "doc_date": when, "content": text}


@pytest.fixture
def corpus(monkeypatch):
    """三份文件對查詢的向量相似度完全相同，排序只剩日期與防護邏輯可以決定。"""
    docs = [doc("old.md", datetime(2026, 8, 1)),
            doc("edge.md", CUTOFF),
            doc("future.md", datetime(2026, 9, 21, 0, 0, 1)),
            doc("undated.md", None)]
    mat = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(docs), 1))
    monkeypatch.setattr(rag, "embed", lambda text: [1.0, 0.0])
    return docs, mat


def paths(hits):
    return {h["path"] for h in hits}


def test_documents_after_the_cutoff_never_appear_even_when_they_match_best(corpus):
    docs, mat = corpus

    hits = rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF)

    assert "future.md" not in paths(hits)


def test_a_document_stamped_exactly_at_the_cutoff_is_still_visible(corpus):
    docs, mat = corpus

    assert "edge.md" in paths(rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF))


def test_an_undated_document_is_excluded_under_a_cutoff_because_its_age_cannot_be_proven(corpus):
    docs, mat = corpus

    assert "undated.md" not in paths(rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF))


def test_without_a_cutoff_behaviour_is_unchanged_and_everything_is_searchable(corpus):
    docs, mat = corpus

    assert paths(rag.search("資料完整度", docs, mat, k=10)) == {"old.md", "edge.md", "future.md", "undated.md"}


def test_a_cutoff_earlier_than_every_dated_document_returns_nothing(corpus):
    docs, mat = corpus

    assert rag.search("資料完整度", docs, mat, k=10, as_of=datetime(2020, 1, 1)) == []


def test_document_age_is_measured_from_the_cutoff_not_from_today(corpus):
    docs, mat = corpus

    hits = {h["path"]: h for h in rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF)}

    assert hits["old.md"]["age_days"] == (CUTOFF - datetime(2026, 8, 1)).days
    assert hits["edge.md"]["age_days"] == 0


def test_the_kind_filter_and_the_cutoff_combine(corpus):
    docs, mat = corpus
    docs[0]["kind"] = "report"

    assert paths(rag.search("資料完整度", docs, mat, k=10, kind="doc", as_of=CUTOFF)) == {"edge.md"}


def test_a_plain_date_means_the_end_of_that_day_and_a_time_is_taken_literally():
    assert rag.parse_as_of("2026-09-20") == datetime(2026, 9, 20, 23, 59, 59, 999999)
    assert rag.parse_as_of("2026-09-20 08:30") == datetime(2026, 9, 20, 8, 30)


def test_an_unparseable_cutoff_is_rejected_instead_of_silently_disabling_the_guard():
    with pytest.raises(ValueError):
        rag.parse_as_of("昨天")


def test_exempt_kinds_ignore_the_cutoff_while_every_other_kind_obeys_it(corpus):
    docs, mat = corpus
    docs[0]["kind"] = "report"      # old.md，本來就在截止前
    docs[2]["kind"] = "report"      # future.md，晚於截止

    hits = rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF, as_of_exempt_kinds=("report",))

    assert "future.md" in paths(hits) and "edge.md" in paths(hits)


def test_an_exempt_kind_without_a_date_is_still_searchable_but_an_undated_non_exempt_one_is_not(corpus):
    docs, mat = corpus
    docs.append(doc("undated-report.md", None, kind="report"))
    mat = np.tile(np.array([[1.0, 0.0]], dtype=np.float32), (len(docs), 1))

    got = paths(rag.search("資料完整度", docs, mat, k=10, as_of=CUTOFF, as_of_exempt_kinds=("report",)))

    assert "undated-report.md" in got and "undated.md" not in got