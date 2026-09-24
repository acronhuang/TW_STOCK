"""專案知識庫頁面的網頁補充判定測試。"""
import pytest

from src.analysis.web_search import needs_web_supplement


@pytest.mark.unit
def test_low_relevance_rag_results_need_web_supplement():
    assert needs_web_supplement([{'vec_sim': 0.55}])