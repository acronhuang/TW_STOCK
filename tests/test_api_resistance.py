"""TDD: /api/resistance——同價位衝高失敗次數，資料不足時明說，不猜。"""

import pytest

from src.api import server
from src.domain.collections import COLL_STOCK_PRICE

pytestmark = pytest.mark.unit


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, projection):
        self.query = query
        return self

    def sort(self, key, direction):
        return self

    def limit(self, n):
        return self.rows[:n]


def bar(day, high=101.0, close=100.5, scale=1.0):
    return {"date": f"2026-09-{day:02d}", "adj_high": high, "adj_close": close, "close": close * scale}


def serve(monkeypatch, rows):
    monkeypatch.setattr(server, "db", {COLL_STOCK_PRICE: FakeCollection(rows[::-1])})  # 資料庫回傳最新在前


def test_three_failed_touches_of_the_same_zone_are_counted(monkeypatch):
    rows = [bar(d) for d in range(1, 41)]
    for index in (-1, -4, -7):
        rows[index] = bar(len(rows) + index + 1, high=110.0, close=105.0)
    serve(monkeypatch, rows)
    got = server.get_resistance("2330")
    assert got["failed_touches"] == 3 and got["block_at"] == 3 and got["window"] == 30
    assert got["zone_high"] == 110.0 and got["as_of"] == "2026-09-40"


def test_a_quiet_stock_has_zero_failed_touches(monkeypatch):
    serve(monkeypatch, [bar(d) for d in range(1, 41)])
    assert server.get_resistance("2330")["failed_touches"] == 0


def test_the_zone_is_reported_in_current_price_units_when_prices_are_adjusted(monkeypatch):
    rows = [bar(d, scale=2.0) for d in range(1, 41)]  # 還原價是現價的一半
    serve(monkeypatch, rows)
    assert server.get_resistance("2330")["zone_high"] == 202.0


def test_too_little_history_is_reported_instead_of_guessed(monkeypatch):
    serve(monkeypatch, [bar(d) for d in range(1, 20)])
    assert server.get_resistance("2330") == {"symbol": "2330", "error": "價格資料不足"}


def test_rows_missing_adjusted_prices_are_dropped_not_zero_filled(monkeypatch):
    rows = [bar(d) for d in range(1, 41)]
    rows[5]["adj_high"] = None
    serve(monkeypatch, rows)
    assert server.get_resistance("2330")["failed_touches"] == 0
    serve(monkeypatch, [{**bar(d), "adj_high": None} for d in range(1, 41)])
    assert server.get_resistance("2330")["error"] == "價格資料不足"


def test_the_minimum_history_is_thirty_five_bars(monkeypatch):
    serve(monkeypatch, [bar(d) for d in range(1, 35)])
    assert "error" in server.get_resistance("2330")
    serve(monkeypatch, [bar(d) for d in range(1, 36)])
    assert "error" not in server.get_resistance("2330")
