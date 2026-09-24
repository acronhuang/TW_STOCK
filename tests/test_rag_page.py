"""專案知識庫頁面的網頁補充判定與路徑外部化測試。"""
from pathlib import Path

import pytest

from src.analysis.web_search import needs_web_supplement

_RAG_PAGE = Path(__file__).resolve().parents[1] / "dashboard" / "pages" / "rag_page.py"


@pytest.mark.unit
def test_low_relevance_rag_results_need_web_supplement():
    assert needs_web_supplement([{'vec_sim': 0.55}])


@pytest.mark.unit
def test_rag_page_has_no_hardcoded_absolute_path():
    """CWE-798: rag_page 不得含硬編碼絕對路徑（Windows 起服務阻斷點）。"""
    src = _RAG_PAGE.read_text(encoding="utf-8")
    assert "/home/mdsadmin" not in src, "rag_page 仍含硬編碼 /home/mdsadmin 路徑"


@pytest.mark.unit
def test_rag_page_resolves_scripts_dir_relatively():
    """scripts 目錄應以 Path(__file__) 相對推導，可跨 OS。"""
    src = _RAG_PAGE.read_text(encoding="utf-8")
    assert "Path(__file__)" in src, "rag_page 未以 Path(__file__) 相對解析 scripts 目錄"