"""BDD: 投資組合管理 (pytest-bdd)"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from src.portfolio.tracker import PortfolioTracker

scenarios('features/portfolio.feature')

TEST_PORTFOLIO = 'bdd_test'


@pytest.fixture
def portfolio():
    from pymongo import MongoClient
    db = MongoClient('mongodb://localhost:27017')['tw_stock_analysis']
    db.portfolio_positions.delete_many({'portfolio': TEST_PORTFOLIO})
    db.portfolio_trades.delete_many({'portfolio': TEST_PORTFOLIO})
    pt = PortfolioTracker(portfolio_name=TEST_PORTFOLIO)
    yield pt
    db.portfolio_positions.delete_many({'portfolio': TEST_PORTFOLIO})
    db.portfolio_trades.delete_many({'portfolio': TEST_PORTFOLIO})


@given('投組 "test" 為空')
def empty_portfolio(portfolio):
    pass


@given('投組 "test" 有持股')
def portfolio_with_holdings(portfolio):
    portfolio.buy('2330', shares=1000, price=900)


@when(parsers.parse('我買入 "{symbol}" {shares:d} 股 @ {price:d} 元'))
def buy_stock(portfolio, symbol, shares, price):
    portfolio.buy(symbol, shares=shares, price=price)


@when(parsers.parse('我再買入 "{symbol}" {shares:d} 股 @ {price:d} 元'))
def buy_more(portfolio, symbol, shares, price):
    portfolio.buy(symbol, shares=shares, price=price)


@when('我查看投組摘要')
def view_summary(portfolio):
    portfolio._summary = portfolio.summary()


@then(parsers.parse('投組應有 {count:d} 支持股'))
def check_count(portfolio, count):
    s = portfolio.summary()
    assert len(s.get('positions', [])) == count


@then(parsers.parse('"{symbol}" 成本應為 {cost:d} 元'))
def check_cost(portfolio, symbol, cost):
    s = portfolio.summary()
    pos = [p for p in s['positions'] if p['symbol'] == symbol]
    assert len(pos) == 1
    assert abs(pos[0]['avg_cost'] - cost) < 0.01


@then('應回傳 positions 清單')
def check_positions(portfolio):
    s = portfolio._summary
    assert 'positions' in s


@then('每支持股有 avg_cost 和 shares')
def check_fields(portfolio):
    for p in portfolio._summary['positions']:
        assert 'avg_cost' in p
        assert 'shares' in p


@then(parsers.parse('"{symbol}" 平均成本應為 {cost:d} 元'))
def check_avg_cost(portfolio, symbol, cost):
    s = portfolio.summary()
    pos = [p for p in s['positions'] if p['symbol'] == symbol]
    assert abs(pos[0]['avg_cost'] - cost) < 0.5


@then(parsers.parse('總股數應為 {shares:d}'))
def check_shares(portfolio, shares):
    s = portfolio.summary()
    total = sum(p['shares'] for p in s['positions'])
    assert total == shares
