"""投資組合追蹤測試"""
import pytest
from src.portfolio.tracker import PortfolioTracker, COLLECTION, TRADE_LOG, DIVIDEND_LOG

TEST_PORTFOLIO = 'pytest_test'


@pytest.fixture
def pt(db):
    """每個測試前清除測試資料"""
    tracker = PortfolioTracker(portfolio_name=TEST_PORTFOLIO)
    db[COLLECTION].delete_many({'portfolio': TEST_PORTFOLIO})
    db[TRADE_LOG].delete_many({'portfolio': TEST_PORTFOLIO})
    db[DIVIDEND_LOG].delete_many({'portfolio': TEST_PORTFOLIO})
    yield tracker
    # 測試後清理
    db[COLLECTION].delete_many({'portfolio': TEST_PORTFOLIO})
    db[TRADE_LOG].delete_many({'portfolio': TEST_PORTFOLIO})
    db[DIVIDEND_LOG].delete_many({'portfolio': TEST_PORTFOLIO})


class TestBuySell:
    @pytest.mark.integration
    def test_buy_creates_position(self, pt):
        pt.buy('0056', lots=5, price=38.0)
        s = pt.summary()
        assert len(s['positions']) == 1
        assert s['positions'][0]['symbol'] == '0056'
        assert s['positions'][0]['shares'] == 5000

    @pytest.mark.integration
    def test_buy_avg_cost(self, pt):
        pt.buy('0056', lots=5, price=38.0)
        pt.buy('0056', lots=5, price=40.0)
        s = pt.summary()
        assert s['positions'][0]['shares'] == 10000
        assert s['positions'][0]['avg_cost'] == 39.0

    @pytest.mark.integration
    def test_sell_reduces_shares(self, pt):
        pt.buy('0056', lots=10, price=38.0)
        pt.sell('0056', lots=5, price=40.0)
        s = pt.summary()
        assert s['positions'][0]['shares'] == 5000

    @pytest.mark.integration
    def test_sell_all_removes_position(self, pt):
        pt.buy('0056', lots=5, price=38.0)
        pt.sell('0056', lots=5, price=40.0)
        s = pt.summary()
        assert len(s['positions']) == 0

    @pytest.mark.integration
    def test_sell_insufficient_raises(self, pt):
        pt.buy('0056', lots=1, price=38.0)
        with pytest.raises(ValueError):
            pt.sell('0056', lots=5, price=40.0)


class TestDividend:
    @pytest.mark.integration
    def test_record_dividend(self, pt):
        pt.buy('0056', lots=10, price=38.0)
        pt.record_dividend('0056', cash_per_share=1.5, ex_date='2026-01-16')
        div = pt.dividend_summary()
        assert div['total_cash_dividend'] == 15000  # 10000 * 1.5

    @pytest.mark.integration
    def test_dividend_tax(self, pt):
        pt.buy('0056', lots=10, price=38.0)
        pt.record_dividend('0056', cash_per_share=2.0)
        div = pt.dividend_summary()
        assert div['tax']['separated_28pct'] == round(20000 * 0.28)


class TestAttribution:
    @pytest.mark.integration
    def test_performance_attribution(self, pt):
        pt.buy('2330', lots=1, price=1800)
        pt.buy('0056', lots=5, price=38.0)
        attr = pt.performance_attribution()
        assert 'error' not in attr
        assert 'portfolio_return' in attr
        assert 'stock_contributions' in attr
        assert len(attr['stock_contributions']) == 2
