"""BDD: 總經分析 (pytest-bdd)"""
import pytest
from pytest_bdd import scenarios, when, then

scenarios('features/macro_analysis.feature')


@pytest.fixture
def macro_result():
    from src.analysis.macro_indicators import MacroAnalyzer
    return {'analyzer': MacroAnalyzer()}


@when('我查詢總經訊號', target_fixture='signal')
def query_signal(macro_result):
    return macro_result['analyzer'].market_signal()


@when('我查詢市場週期', target_fixture='cycle')
def query_cycle():
    from src.strategy.trading_rules import TradingRules
    return TradingRules().market_cycle()


@when('我查詢總經概覽', target_fixture='overview')
def query_overview(macro_result):
    return macro_result['analyzer'].overview()


@then('應回傳 score（-100 到 +100）')
def check_score(signal):
    assert -100 <= signal['score'] <= 100


@then(pytest.mark.parametrize('', [None])('應回傳 verdict（偏多/偏空/中性）') if False else
      '應回傳 verdict（偏多/偏空/中性）')
def check_verdict(signal):
    assert any(k in signal['verdict'] for k in ['偏多', '偏空', '中性'])


@then('應回傳 cycle（spring/summer/autumn/winter）')
def check_cycle(cycle):
    assert cycle['cycle'] in ('spring', 'summer', 'autumn', 'winter', 'unknown')


@then('應回傳建議倉位比例')
def check_position(cycle):
    assert 'suggested_position' in cycle


@then('應包含 foreign_net_5d（外資近 5 日買賣超）')
def check_foreign(overview):
    taiex = overview.get('taiex', {})
    assert 'foreign_net_5d' in taiex


@then('應包含 etf_0050 價格')
def check_0050(overview):
    taiex = overview.get('taiex', {})
    assert 'etf_0050' in taiex
    assert taiex['etf_0050'] > 0
