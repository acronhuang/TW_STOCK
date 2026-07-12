"""BDD step implementations for stock_ranking.feature"""
import pytest

pytestmark = pytest.mark.integration


class TestStockRankingBDD:
    """Feature: 股票綜合排行"""

    def test_basic_ranking_returns_correct_count(self, ranker):
        """Scenario: 基本排行產出"""
        results = ranker.rank(limit=10, financial_check=False)
        assert len(results) == 10
        assert all('total_score' in r for r in results)
        scores = [r['total_score'] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_financial_filter_removes_unhealthy(self, ranker):
        """Scenario: 財報篩檢過濾地雷股"""
        from src.analysis.financial_filter import FinancialFilter
        ff = FinancialFilter()
        results = ranker.rank(limit=10, financial_check=True)
        for r in results:
            assert ff.is_healthy(r['symbol']), \
                f"{r['symbol']} 通過排行但未通過財報篩檢"

    def test_pe_range_filter(self, ranker):
        """Scenario: PE 範圍過濾"""
        results = ranker.rank(limit=10, min_pe=5, max_pe=20, financial_check=False)
        for r in results:
            pe = r['metrics'].get('pe_ratio')
            if pe:
                assert 5 <= pe <= 20, f"{r['symbol']} PE={pe} 超出範圍"
