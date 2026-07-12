"""同業比較測試"""
import pytest
from src.analysis.peer_comparison import PeerComparison


@pytest.fixture(scope="module")
def pc():
    return PeerComparison()


class TestPeerAnalysis:
    @pytest.mark.integration
    def test_analyze_2330(self, pc):
        result = pc.analyze('2330')
        assert 'error' not in result
        assert result['industry'] == '半導體業'
        assert result['peer_count'] > 10
        assert len(result['comparisons']) > 0
        assert result['composite']['score'] >= 0

    @pytest.mark.integration
    def test_comparisons_have_rank(self, pc):
        result = pc.analyze('2330')
        for c in result['comparisons']:
            if c.get('rank'):
                assert c['rank'] >= 1
                assert c['percentile'] >= 0
                assert c['percentile'] <= 100


class TestIndustryRanking:
    @pytest.mark.integration
    def test_semiconductor_ranking(self, pc):
        result = pc.industry_ranking('半導體業', limit=10)
        assert 'error' not in result
        assert result['total_stocks'] > 10
        assert len(result['ranking']) <= 10
        assert result['ranking'][0]['score'] >= result['ranking'][-1]['score']

    @pytest.mark.integration
    def test_list_industries(self, pc):
        industries = pc.list_industries()
        assert len(industries) > 10
        names = [i['industry'] for i in industries]
        assert '半導體業' in names
