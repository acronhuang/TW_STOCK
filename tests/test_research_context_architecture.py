"""TDD: 研究上下文核心保持平台中立，且 SDD 可追溯至測試。"""

from pathlib import Path


def test_sdd_lists_all_core_test_files():
    source = Path("docs/designs/2026-10-09-research-context-sdd.md").read_text(encoding="utf-8")

    for test_file in (
        "tests/test_research_context_models.py",
        "tests/test_research_context_repository.py",
        "tests/test_research_context_retriever.py",
        "tests/test_research_context_builder.py",
        "tests/test_research_context_architecture.py",
    ):
        assert test_file in source


def test_research_context_core_has_no_platform_imports():
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src/research_context").glob("*.py")
    )

    assert "import streamlit" not in source
    assert "from fastapi" not in source
    assert "dify" not in source.lower()