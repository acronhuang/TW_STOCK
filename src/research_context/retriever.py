"""既有 RAG 搜尋的快取與 citation 邊界。"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.research_context.models import RagCitation


class RagRetriever:
    def __init__(
        self,
        load_fn: Callable[[], tuple[Any, Any]],
        search_fn: Callable[..., list[dict[str, Any]]],
        clock: Callable[[], float],
        ttl_seconds: float = 600,
    ) -> None:
        self._load_fn = load_fn
        self._search_fn = search_fn
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._docs: Any = None
        self._matrix: Any = None
        self._loaded_at: float | None = None

    def search(self, question: str, max_sources: int) -> list[RagCitation]:
        docs, matrix = self._corpus()
        rows = self._search_fn(question, docs, matrix, k=max_sources)
        return [self._citation(row) for row in rows[:max_sources]]

    def _corpus(self) -> tuple[Any, Any]:
        now = self._clock()
        if self._loaded_at is None or now - self._loaded_at >= self._ttl_seconds:
            self._docs, self._matrix = self._load_fn()
            self._loaded_at = now
        return self._docs, self._matrix

    @staticmethod
    def _citation(row: dict[str, Any]) -> RagCitation:
        path = str(row.get("path", ""))
        chunk_idx = int(row.get("chunk_idx", 0))
        return RagCitation(
            id=f"rag:{path}:{chunk_idx}",
            title=str(row.get("title", "")),
            path=path,
            chunk_idx=chunk_idx,
            document_date=_date_text(row.get("doc_date")),
            age_days=int(row.get("age_days", 0)),
            score=float(row.get("score", 0.0)),
            excerpt=str(row.get("content", ""))[:500],
        )


def _date_text(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10] if value is not None else None