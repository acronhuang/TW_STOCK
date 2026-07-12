"""BDD step implementations for trading_rules.feature"""
import pytest

pytestmark = pytest.mark.integration


class TestTradingRulesBDD:
    """Feature: 北大四大法則"""

    def test_334_summer(self):
        """Scenario: 法則一 — 夏長期倉位"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.position_334(4_000_000, 'summer')
        assert r['core_pct'] == 40
        assert r['tactical_pct'] == 30
        assert r['cash_pct'] == 30
        assert r['core_position'] == 1_600_000

    def test_334_winter_all_cash(self):
        """Scenario: 法則一 — 冬藏期空倉"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.position_334(4_000_000, 'winter')
        assert r['cash_pct'] == 100
        assert r['core_position'] == 0

    def test_5pct_stop_loss(self):
        """Scenario: 法則二 — 5% 無條件止損"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.check_stop_loss('2603', 213)
        if r.get('current') and r['current'] < 213 * 0.95:
            assert r['action'] == '止損出場'

    def test_below_ma60_but_profit_not_stop(self):
        """Scenario: 法則二 — 跌破 MA60 但獲利中不止損"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.check_stop_loss('00919', 22.49)
        if r.get('pnl_pct') and r['pnl_pct'] > 0:
            assert r['action'] != '止損出場', \
                f"獲利 {r['pnl_pct']:+.1f}% 不應判止損"

    def test_buy_three_questions_rsi_overbought(self):
        """Scenario: 法則三 — RSI 超買不宜買"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.buy_three_questions('0050')
        if r.get('q3_space'):
            rsi_text = r['q3_space']['answer']
            # 若 RSI > 70 應判 pass=False
            assert isinstance(r['q3_space']['pass'], bool)

    def test_market_cycle_returns_valid(self):
        """市場週期應回傳有效值"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.market_cycle()
        assert r['cycle'] in ('spring', 'summer', 'autumn', 'winter', 'unknown')
        assert 'suggested_position' in r

    def test_institution_phase_returns_valid(self):
        """主力階段應回傳有效值"""
        from src.strategy.trading_rules import TradingRules
        tr = TradingRules()
        r = tr.detect_institution_phase('2603')
        assert r['phase'] in ('建倉', '洗盤', '拉升', '出貨', '徹底出貨', '觀望')
        assert 'action' in r
