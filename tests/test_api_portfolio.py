"""TDD: 持倉唯讀端點——只能讀、種類固定、日期與 Decimal128 轉成純值。"""

from datetime import datetime

import pytest
from bson import Decimal128
from fastapi import HTTPException

from src.api import server

pytestmark = pytest.mark.unit


class FakeCursor:
    def __init__(self, rows, log):
        self.rows, self.log = list(rows), log

    def sort(self, key, direction):
        self.log.append(("sort", key, direction))
        return self

    def limit(self, count):
        self.log.append(("limit", count))
        self.rows = self.rows[:count]
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeCollection:
    def __init__(self, rows, log):
        self.rows, self.log = rows, log

    def find(self, query, projection):
        self.log.append(("find", query, projection))
        return FakeCursor(self.rows, self.log)


class FakeDb:
    def __init__(self, rows):
        self.rows, self.log = rows, []

    def __getitem__(self, name):
        self.log.append(("collection", name))
        return FakeCollection(self.rows, self.log)


@pytest.fixture
def fake(monkeypatch):
    db = FakeDb([{"symbol": "2330", "shares": 1000, "avg_cost": Decimal128("30.5"), "updated_at": datetime(2026, 9, 4, 22, 24, 11),
                  "buy_date": datetime(2023, 3, 15), "note": "備註"}])
    monkeypatch.setattr(server, "db", db)
    return db


@pytest.mark.parametrize("kind,collection,key,direction", [
    ("positions", "portfolio_positions", "symbol", 1),
    ("lots", "portfolio_lots", "buy_date", -1),
    ("trades", "portfolio_trades", "date", -1),
])
def test_each_kind_reads_its_own_collection_in_a_fixed_order(fake, kind, collection, key, direction):
    server.get_portfolio(kind, 200)

    assert ("collection", collection) in fake.log and ("sort", key, direction) in fake.log


def test_the_query_has_no_filter_and_never_returns_the_internal_id(fake):
    server.get_portfolio("positions", 200)

    assert ("find", {}, {"_id": 0}) in fake.log


def test_dates_and_decimals_become_plain_values_and_other_values_are_untouched(fake):
    row = server.get_portfolio("positions", 200)[0]

    assert row["avg_cost"] == 30.5 and isinstance(row["avg_cost"], float)
    assert row["buy_date"] == "2023-03-15" and row["updated_at"] == "2026-09-04 22:24:11"
    assert row["symbol"] == "2330" and row["shares"] == 1000 and row["note"] == "備註"


def test_the_limit_is_forwarded(fake):
    fake.rows = [{"symbol": str(i)} for i in range(10)]

    assert len(server.get_portfolio("positions", 3)) == 3 and ("limit", 3) in fake.log


@pytest.mark.parametrize("kind", ["other", "", "positions/x", "../x", "portfolio_positions"])
def test_an_unknown_kind_is_a_404_and_never_touches_the_database(fake, kind):
    with pytest.raises(HTTPException) as caught:
        server.get_portfolio(kind, 200)

    assert caught.value.status_code == 404 and fake.log == []


def test_the_route_is_registered_once_and_is_get_only():
    routes = [r for r in server.app.routes if getattr(r, "path", "") == "/api/portfolio/{kind}"]

    assert len(routes) == 1 and routes[0].methods == {"GET"}
