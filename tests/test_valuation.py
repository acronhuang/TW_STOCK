"""估值模型測試"""
import pytest
from src.analysis.valuation_models import ValuationAnalyzer


@pytest.fixture(scope="module")
def va():
    return ValuationAnalyzer()


class TestDCF:
    @pytest.mark.integration
    def test_dcf_returns_fair_value(self, va, sample_symbol):
        result = va.dcf_valuation(sample_symbol)
        assert result is not None
        if result.get('fair_value'):
            assert result['fair_value'] > 0
            assert 'wacc' in result
            assert 'beta' in result
            assert result['beta'] > 0

    @pytest.mark.integration
    def test_dcf_invalid_symbol_returns_none(self, va):
        result = va.dcf_valuation('9999')
        assert result is None


class TestDDM:
    @pytest.mark.integration
    def test_ddm_returns_fair_value(self, va, sample_symbol):
        result = va.ddm_valuation(sample_symbol)
        assert result is not None
        if result.get('fair_value'):
            assert result['fair_value'] > 0
            assert 'cost_of_equity' in result
            assert 'dividend_history' in result

    @pytest.mark.integration
    def test_ddm_etf(self, va):
        """ETF (0056) 應有股利資料"""
        result = va.ddm_valuation('0056')
        assert result is not None


class TestPEBand:
    @pytest.mark.integration
    def test_pe_band_analysis(self, va, sample_symbol):
        result = va.pe_band_analysis(sample_symbol)
        assert result is not None
        if result.get('fair_value'):
            assert result['fair_value'] > 0
            assert result['pe_percentile'] >= 0
            assert result['pe_percentile'] <= 100
            assert result['zone'] in ['便宜區', '偏低區', '合理區', '偏高區', '昂貴區']


class TestComposite:
    @pytest.mark.integration
    def test_full_analysis(self, va, sample_symbol):
        result = va.analyze(sample_symbol)
        assert 'symbol' in result
        assert 'composite' in result
        assert result['composite']['models_used'] >= 1
        assert result['composite']['verdict'] in [
            '嚴重低估', '低估', '略為低估', '合理',
            '略為高估', '高估', '嚴重高估', '無法判定'
        ]
