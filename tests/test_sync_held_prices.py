"""TDD: 持倉但日常管線不收的代號（如債券 ETF 00679B）改由 FinMind 補價，避免持倉估值停在舊價。"""

from datetime import datetime

from bson.decimal128 import Decimal128

import pytest

from scripts import sync_held_prices as shp

pytestmark = pytest.mark.unit


def finmind_row(date="2026-10-08", close=27.5, volume=1000, **extra):
    return {"date": date, "stock_id": "00679B", "Trading_Volume": volume, "Trading_money": 27500000, "open": 27.4,
            "max": 27.6, "min": 27.3, "close": close, "spread": 0.1, "Trading_turnover": 321, **extra}


def test_a_finmind_row_becomes_a_stock_price_document_with_the_existing_schema():
    doc = shp.to_doc("00679B", finmind_row())

    assert doc["symbol"] == doc["stock_id"] == "00679B" and doc["date"] == datetime(2026, 10, 8)
    assert doc["close"] == Decimal128("27.5") and doc["high"] == Decimal128("27.6") and doc["low"] == Decimal128("27.3")
    assert doc["volume"] == Decimal128("1000") and doc["amount"] == "27500000" and doc["transaction"] == "321"
    assert doc["data_source"] == "FinMind:TaiwanStockPrice"


def test_a_day_without_a_close_is_not_written():
    assert shp.to_doc("00679B", finmind_row(close=0)) is None


def test_only_days_after_the_last_stored_price_are_requested():
    assert shp.start_after(datetime(2026, 4, 1), datetime(2026, 10, 8)) == "2026-04-02"
    assert shp.start_after(datetime(2026, 10, 8), datetime(2026, 10, 8)) is None


def test_the_adjusted_prices_are_only_set_on_insert_so_a_later_dividend_adjustment_is_not_overwritten():
    op = shp.build_operation(shp.to_doc("00679B", finmind_row()))

    assert op._filter == {"symbol": "00679B", "date": datetime(2026, 10, 8)} and op._upsert is True
    assert "adj_close" not in op._doc["$set"] and op._doc["$setOnInsert"]["adj_close"] == Decimal128("27.5")
    assert op._doc["$setOnInsert"]["adjustment_factor"] == Decimal128("1.0")
