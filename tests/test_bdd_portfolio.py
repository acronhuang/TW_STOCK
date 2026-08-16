"""BDD: 投資組合管理 (pytest-bdd)

2026-08-17 改指向 src/portfolio/lots.py。原本測的是 PortfolioTracker,
但它已退役(寫 portfolio_trades,該表已凍結為歷史快照)。這 3 個情境描述的行為
——買入登記、投組摘要、多次加碼平均成本——現在由 lots.py 實作,
所以 feature 檔一字未改,只換掉步驟定義指向的元件。

🔴 隔離:lots.replace_lots 是 delete_many({}) 全刪重寫,**沒有投組名稱過濾**。
在 production DB 上跑會清掉真實持倉,所以一律用獨立測試 DB,並在 fixture 裡
硬性擋掉 production 名稱。原本的 tracker 版用 portfolio 欄位過濾共用同一個 DB,
換元件後那層保護不存在了。
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from src.portfolio import lots as L

scenarios('features/portfolio.feature')

TEST_DB = 'tw_stock_analysis_bddtest'
PROD_DB = 'tw_stock_analysis'


class _Book:
    """累積分批,每次變動後重算彙總 —— 對應使用者在風控頁編輯表格後存檔。"""

    def __init__(self, db):
        self.db = db
        self.rows = []

    def buy(self, symbol, shares, price):
        self.rows.append({"symbol": symbol, "buy_date": None,
                          "shares": shares, "price": price,
                          "category": "波段", "kind": "trade"})
        L.replace_lots(self.db, self.rows)

    def summary(self):
        return {"positions": list(self.db.portfolio_positions.find({}, {"_id": 0}))}


@pytest.fixture
def portfolio():
    from pymongo import MongoClient
    cli = MongoClient('mongodb://localhost:27017')
    assert TEST_DB != PROD_DB, "測試 DB 不得為 production"
    cli.drop_database(TEST_DB)
    yield _Book(cli[TEST_DB])
    cli.drop_database(TEST_DB)


@given('投組 "test" 為空')
def empty_portfolio(portfolio):
    assert portfolio.summary()['positions'] == []


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
    assert len(portfolio.summary()['positions']) == count


@then(parsers.parse('"{symbol}" 成本應為 {cost:d} 元'))
def check_cost(portfolio, symbol, cost):
    pos = [p for p in portfolio.summary()['positions'] if p['symbol'] == symbol]
    assert len(pos) == 1
    assert abs(pos[0]['avg_cost'] - cost) < 0.01


@then('應回傳 positions 清單')
def check_positions(portfolio):
    assert 'positions' in portfolio._summary


@then('每支持股有 avg_cost 和 shares')
def check_fields(portfolio):
    for p in portfolio._summary['positions']:
        assert 'avg_cost' in p
        assert 'shares' in p


@then(parsers.parse('"{symbol}" 平均成本應為 {cost:d} 元'))
def check_avg_cost(portfolio, symbol, cost):
    pos = [p for p in portfolio.summary()['positions'] if p['symbol'] == symbol]
    assert abs(pos[0]['avg_cost'] - cost) < 0.5


@then(parsers.parse('總股數應為 {shares:d}'))
def check_shares(portfolio, shares):
    assert sum(p['shares'] for p in portfolio.summary()['positions']) == shares
