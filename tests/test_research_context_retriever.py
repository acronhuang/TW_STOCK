"""TDD: 研究上下文 RAG 快取與 citation 轉換。"""

from datetime import datetime

import pytest

from src.research_context.retriever import RagRetriever


pytestmark = pytest.mark.unit


def test_retriever_reuses_corpus_until_ttl_expires():
    calls = {"load": 0, "search": 0}
    now = {"value": 0.0}

    def load():
        calls["load"] += 1
        return ([{"path": "docs/a.md"}], object())

    def search(*_args, **_kwargs):
        calls["search"] += 1
        return []

    retriever = RagRetriever(load, search, lambda: now["value"], ttl_seconds=600)

    retriever.search("第一題", 4)
    retriever.search("第二題", 4)
    now["value"] = 600.0
    retriever.search("第三題", 4)

    assert calls == {"load": 2, "search": 3}


def test_retriever_passes_source_limit_and_returns_allowlisted_citations():
    seen = {}
    long_content = "a" * 600

    def search(query, docs, matrix, *, k):
        seen.update({"query": query, "docs": docs, "matrix": matrix, "k": k})
        return [
            {
                "path": "docs/first.md",
                "chunk_idx": 2,
                "title": "第一份文件",
                "doc_date": datetime(2026, 10, 8),
                "age_days": 1,
                "score": 0.032,
                "content": long_content,
                "embedding": [0.1, 0.2],
                "internal_note": "must not escape",
            },
            {
                "path": "docs/second.md",
                "chunk_idx": 0,
                "title": "第二份文件",
                "doc_date": None,
                "age_days": 0,
                "score": 0.021,
                "content": "第二段",
            },
        ]

    docs = [{"path": "docs/a.md"}]
    matrix = object()
    retriever = RagRetriever(lambda: (docs, matrix), search, lambda: 1.0)

    citations = retriever.search("測試問題", 2)

    assert seen == {"query": "測試問題", "docs": docs, "matrix": matrix, "k": 2}
    assert [citation.id for citation in citations] == [
        "rag:docs/first.md:2",
        "rag:docs/second.md:0",
    ]
    assert citations[0].document_date == "2026-10-08"
    assert citations[0].excerpt == long_content[:500]
    assert citations[1].excerpt == "第二段"
    assert citations[0].model_dump() == {
        "id": "rag:docs/first.md:2",
        "title": "第一份文件",
        "path": "docs/first.md",
        "chunk_idx": 2,
        "document_date": "2026-10-08",
        "age_days": 1,
        "score": 0.032,
        "excerpt": long_content[:500],
    }


def test_retriever_propagates_rag_failure():
    def search(*_args, **_kwargs):
        raise RuntimeError("rag unavailable")

    retriever = RagRetriever(lambda: ([{"path": "docs/a.md"}], object()), search, lambda: 1.0)

    with pytest.raises(RuntimeError, match="rag unavailable"):
        retriever.search("測試問題", 4)


def test_retriever_enforces_source_limit_when_search_returns_extra_rows():
    rows = [
        {
            "path": f"docs/{index}.md",
            "chunk_idx": 0,
            "title": f"文件 {index}",
            "age_days": 0,
            "score": 0.1,
            "content": "證據",
        }
        for index in range(3)
    ]
    retriever = RagRetriever(lambda: ([{"path": "docs/a.md"}], object()), lambda *_args, **_kwargs: rows, lambda: 1.0)

    citations = retriever.search("測試問題", 1)

    assert [citation.id for citation in citations] == ["rag:docs/0.md:0"]