"""風險管理模組測試"""
import pytest
from src.analysis.risk_manager import RiskAnalyzer


@pytest.fixture(scope="module")
def ra():
    return RiskAnalyzer()


class TestStockRisk:
    @pytest.mark.integration
    def test_analyze_returns_metrics(self, ra, sample_symbol):
        result = ra.analyze(sample_symbol)
        assert 'error' not in result
        assert result['data_points'] >= 30
        assert 'var' in result
        assert result['var']['daily_var_95'] > 0
        assert result['var']['daily_var_99'] > result['var']['daily_var_95']

    @pytest.mark.integration
    def test_sharpe_ratio_type(self, ra, sample_symbol):
        result = ra.analyze(sample_symbol)
        assert isinstance(result['ratios']['sharpe'], float)
        assert isinstance(result['ratios']['beta'], float)
        assert 0.3 <= result['ratios']['beta'] <= 3.0

    @pytest.mark.integration
    def test_risk_level_valid(self, ra, sample_symbol):
        result = ra.analyze(sample_symbol)
        assert result['risk_level']['level'] in ['低風險', '中風險', '高風險', '極高風險']

    @pytest.mark.integration
    def test_invalid_symbol(self, ra):
        result = ra.analyze('XXXX')
        assert 'error' in result


class TestPortfolioRisk:
    @pytest.mark.integration
    def test_portfolio_risk(self, ra):
        result = ra.portfolio_risk(['2330', '2317', '0056'], [0.5, 0.3, 0.2])
        assert 'error' not in result
        assert result['portfolio']['annual_volatility'] > 0
        assert result['portfolio']['sharpe'] is not None
        assert result['diversification_ratio'] >= 1.0

    @pytest.mark.integration
    def test_correlation_matrix(self, ra):
        result = ra.portfolio_risk(['2330', '0056'])
        matrix = result['correlation_matrix']['matrix']
        assert matrix[0][0] == 1.0  # 自相關 = 1
        assert matrix[1][1] == 1.0
        assert -1 <= matrix[0][1] <= 1  # 相關係數範圍


class TestPositionSize:
    @pytest.mark.integration
    def test_position_size(self, ra):
        result = ra.position_size('0056', capital=1_000_000)
        assert 'error' not in result
        assert result['recommended']['lots'] >= 0
        assert result['recommended']['stop_loss_price'] < result['price']
