"""_get_trailing_eps 加總邏輯單元測試 —— 取代原脆弱的「2706 EPS>1.0」硬編碼門檻。

原 tests/features/steps/test_valuation_steps.py::test_ttm_eps_direct_sum 以特定個股的
EPS 數值(>1.0, <5.0)當斷言，隨真實財報漂移即失敗(實測 2706 TTM=0.67 → 紅)。
本檔改測「最近 4 季直接加總」的邏輯本身，用 fake db，不需 MongoDB，可在任意環境執行。
"""
import pytest

from src.analysis.valuation_models import ValuationAnalyzer


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self._docs[:n]


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *a, **k):
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, docs):
        self.quarterly_earnings = _FakeColl(docs)


def _analyzer_with(docs):
    """不呼叫 __init__（避免連 Mongo），直接注入 fake db。"""
    a = ValuationAnalyzer.__new__(ValuationAnalyzer)
    a.db = _FakeDB(docs)
    return a


@pytest.mark.unit
def test_ttm_eps_is_sum_of_4_latest_quarters():
    docs = [  # 已按 year/season desc 排序
        {'year': 2025, 'season': 2, 'income': {'eps': 1.0}},
        {'year': 2025, 'season': 1, 'income': {'eps': 2.0}},
        {'year': 2024, 'season': 4, 'income': {'eps': 3.0}},
        {'year': 2024, 'season': 3, 'income': {'eps': 4.0}},
        {'year': 2024, 'season': 2, 'income': {'eps': 9.0}},  # 第5筆不計入
    ]
    assert _analyzer_with(docs)._get_trailing_eps('X') == pytest.approx(10.0)


@pytest.mark.unit
def test_ttm_eps_handles_negative_quarters():
    """虧損季(負 EPS)也應正確加總，不受磁碟門檻限制。"""
    docs = [
        {'year': 2025, 'season': 2, 'income': {'eps': -0.5}},
        {'year': 2025, 'season': 1, 'income': {'eps': 0.3}},
        {'year': 2024, 'season': 4, 'income': {'eps': 0.4}},
        {'year': 2024, 'season': 3, 'income': {'eps': 0.5}},
    ]
    assert _analyzer_with(docs)._get_trailing_eps('X') == pytest.approx(0.7)


@pytest.mark.unit
def test_ttm_eps_none_when_insufficient_quarters():
    docs = [{'year': 2025, 'season': 2, 'income': {'eps': 1.0}}]
    assert _analyzer_with(docs)._get_trailing_eps('X') is None


@pytest.mark.unit
def test_ttm_eps_none_when_missing_eps():
    docs = [
        {'year': 2025, 'season': 2, 'income': {'eps': 1.0}},
        {'year': 2025, 'season': 1, 'income': {}},  # 缺 eps
        {'year': 2024, 'season': 4, 'income': {'eps': 3.0}},
        {'year': 2024, 'season': 3, 'income': {'eps': 4.0}},
    ]
    assert _analyzer_with(docs)._get_trailing_eps('X') is None
