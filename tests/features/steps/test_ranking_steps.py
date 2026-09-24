"""BDD step implementations for stock_ranking.feature"""
import pytest

# 基底標 integration;每測分別標 needs_data(不變式,可種子)或 prod_data。
# 種子擴到 10 檔非-ETF 個股(scripts/seed_test_data.py)→ rank(limit=10) 可滿 10 筆。
pytestmark = pytest.mark.integration


class TestStockRankingBDD:
    """Feature: 股票綜合排行"""

    @pytest.mark.needs_data
    def test_basic_ranking_returns_correct_count(self, ranker):
        """Scenario: 基本排行產出(筆數=limit + 分數遞減不變式)"""
        results = ranker.rank(limit=10, financial_check=False)
        assert len(results) == 10
        assert all('total_score' in r for r in results)
        scores = [r['total_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.prod_data
    def test_financial_filter_removes_unhealthy(self, ranker):
        """Scenario: 財報篩檢過濾地雷股(依賴真實財報健康判定 → live-only)"""
        from src.analysis.financial_filter import FinancialFilter
        ff = FinancialFilter()
        results = ranker.rank(limit=10, financial_check=True)
        for r in results:
            assert ff.is_healthy(r['symbol']), \
                f"{r['symbol']} 通過排行但未通過財報篩檢"

    @pytest.mark.needs_data
    def test_pe_range_filter(self, ranker):
        """Scenario: PE 範圍過濾(守衛式 if pe)"""
        results = ranker.rank(limit=10, min_pe=5, max_pe=20, financial_check=False)
        for r in results:
            pe = r['metrics'].get('pe_ratio')
            if pe:
                assert 5 <= pe <= 20, f"{r['symbol']} PE={pe} 超出範圍"
