"""財報健康分析測試"""
import pytest

# ADR-0011 分類（2026-08-16）：斷言真實公司的財務數字（台積電評等/ROE/EPS、三商餐飲警示），
# 公司狀況一變就紅而程式無誤 —— 依 ADR-0011 屬「世界的事實」不進迴歸閘
pytestmark = pytest.mark.integration


class TestFinancialHealth:
    def test_tsmc_grade_A(self, health):
        r = health.analyze_stock('2330')
        assert 'error' not in r
        assert r['total_score'] > 70
        assert 'A' in r['grade']

    def test_dupont_roe(self, health):
        r = health.analyze_stock('2330')
        dup = r.get('dupont', {})
        if dup.get('roe_pct'):
            assert dup['roe_pct'] > 10, "台積電 ROE 應 > 10%"

    def test_ttm_eps_positive(self, health):
        r = health.analyze_stock('2330')
        assert r['ttm']['eps'] > 50, "台積電 TTM EPS 應 > 50"

    def test_invalid_symbol(self, health):
        r = health.analyze_stock('9999')
        assert 'error' in r

    def test_warnings_for_weak_stock(self, health):
        r = health.analyze_stock('7705')
        if 'error' not in r:
            assert len(r.get('warnings', [])) > 0, "三商餐飲應有警示"


class TestFinancialFilter:
    def test_healthy_stock(self):
        from src.analysis.financial_filter import FinancialFilter
        ff = FinancialFilter()
        assert ff.is_healthy('2330') is True

    def test_unhealthy_stock(self):
        from src.analysis.financial_filter import FinancialFilter
        ff = FinancialFilter()
        r = ff.check('7705')
        assert isinstance(r['healthy'], bool)
