"""北大四大法則測試"""
import pytest
from src.strategy.trading_rules import TradingRules


@pytest.fixture(scope="module")
def rules():
    return TradingRules()


class TestPositionSizing:
    def test_334_normal(self, rules):
        r = rules.position_334(1_000_000)
        assert r['core_position'] == 300_000
        assert r['tactical_position'] == 300_000
        assert r['cash_reserve'] == 400_000

    def test_334_winter(self, rules):
        r = rules.position_334(1_000_000, 'winter')
        assert r['cash_pct'] == 100
        assert r['core_position'] == 0

    def test_334_summer(self, rules):
        r = rules.position_334(1_000_000, 'summer')
        assert r['core_pct'] == 40


class TestStopLoss:
    def test_stop_loss_returns_action(self, rules):
        r = rules.check_stop_loss('2330', 1000)
        assert 'action' in r
        assert r['action'] in ('持有', '止損出場', '減碼觀察', '留意趨勢')

    def test_profit_not_stop(self, rules):
        r = rules.check_stop_loss('00919', 22.49)
        if r.get('pnl_pct', 0) > 0:
            assert r['action'] != '止損出場'


class TestBuyThreeQuestions:
    def test_three_questions_format(self, rules):
        r = rules.buy_three_questions('2330')
        assert 'q1_why' in r
        assert 'q2_who' in r
        assert 'q3_space' in r
        assert 'pass' in r['q1_why']


class TestMarketCycle:
    def test_cycle_valid(self, rules):
        r = rules.market_cycle()
        assert r['cycle'] in ('spring', 'summer', 'autumn', 'winter', 'unknown')

    def test_cycle_has_position(self, rules):
        r = rules.market_cycle()
        assert 'suggested_position' in r


class TestInstitutionPhase:
    def test_phase_valid(self, rules):
        r = rules.detect_institution_phase('2603')
        assert r['phase'] in ('建倉', '洗盤', '拉升', '出貨', '徹底出貨', '觀望')
        assert 'action' in r
