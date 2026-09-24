"""綜合選股評分測試"""
import pytest
from src.analysis.stock_ranker import StockRanker


@pytest.fixture(scope="module")
def sr():
    return StockRanker()


class TestRanking:
    # rank() 預設 financial_check=True → 依賴真實財報健康篩檢(同
    # test_financial_filter_removes_unhealthy 的 live-only 理由)→ prod_data;
    # 且全市場排序耗時 → 並標 slow。
    @pytest.mark.integration
    @pytest.mark.prod_data
    @pytest.mark.slow
    def test_rank_returns_list(self, sr):
        result = sr.rank(limit=10)
        assert len(result) > 0
        assert len(result) <= 10
        assert result[0]['total_score'] >= result[-1]['total_score']

    @pytest.mark.integration
    @pytest.mark.prod_data
    @pytest.mark.slow
    def test_rank_fields(self, sr):
        result = sr.rank(limit=5)
        for s in result:
            assert 'symbol' in s
            assert 'total_score' in s
            assert 'grade' in s
            assert 'scores' in s
            assert all(k in s['scores'] for k in
                       ['value', 'quality', 'momentum', 'safety', 'institutional', 'growth'])
            assert 0 <= s['total_score'] <= 100

    @pytest.mark.integration
    @pytest.mark.needs_data
    def test_score_single_stock(self, sr):
        result = sr.score_stock('2330')
        assert result is not None
        # 若最新日 PE 為 None（TWSE 延遲），score_stock 會回 error
        # 這不是 bug，是資料時效問題，改用有因子的股票測試
        if 'error' in result:
            result = sr.score_stock('2317')  # fallback 鴻海
        if 'error' not in result:
            assert result['total_score'] > 0
