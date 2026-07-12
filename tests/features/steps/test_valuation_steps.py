"""BDD step implementations for valuation.feature"""
import pytest

pytestmark = pytest.mark.integration


class TestValuationBDD:
    """Feature: 估值分析"""

    def test_dcf_returns_fair_value_with_min_wacc(self, valuation):
        """Scenario: DCF 估值 — WACC 不低於 8%"""
        r = valuation.analyze('2330')
        dcf = r.get('dcf', {})
        if dcf.get('fair_value'):
            assert dcf['fair_value'] > 0
            assert dcf.get('wacc', 0) >= 8.0, f"WACC {dcf['wacc']}% < 8%"

    def test_ddm_growth_cap(self, valuation):
        """Scenario: DDM 股利成長率不超過 5%"""
        r = valuation.analyze('2892')
        ddm = r.get('ddm', {})
        if ddm.get('div_growth_rate') is not None:
            assert ddm['div_growth_rate'] <= 5.0, \
                f"股利成長率 {ddm['div_growth_rate']}% > 5% 上限"

    def test_pe_band_max_25(self, valuation):
        """Scenario: PE Band PE 中位數不超過 25 倍"""
        r = valuation.analyze('1229')
        pe = r.get('pe_band', {})
        if pe.get('pe_stats'):
            p50 = pe['pe_stats'].get('p50', 0)
            assert p50 <= 25, f"PE P50={p50} > 25 上限"
        if pe.get('zone'):
            assert pe['zone'] in ('便宜區', '偏低區', '合理區', '偏高區', '昂貴區')

    def test_ttm_eps_direct_sum(self, valuation):
        """Scenario: TTM EPS 直接加總 4 季"""
        eps = valuation._get_trailing_eps('2706')
        assert eps is not None
        assert eps > 1.0, f"2706 TTM EPS={eps}，應 > 1.0（4 季加總）"
        assert eps < 5.0, f"2706 TTM EPS={eps}，異常偏高"

    def test_invalid_symbol_returns_error(self, valuation):
        """Scenario: 無資料時不編造數字"""
        r = valuation.analyze('9999')
        assert r.get('error') or r['composite'].get('fair_value') is None
