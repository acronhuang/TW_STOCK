"""TDD: 興櫃每日行情（TPEX tpex_esb_latest_statistics，只提供最新交易日）。"""

from datetime import datetime

import pytest

from src.ingest import emerging

pytestmark = pytest.mark.unit

ROW = {"Date": "1151008", "Time": "163005", "SecuritiesCompanyCode": "1260", "CompanyName": "富味鄉",
       "PreviousAveragePrice": "31.7", "BuyingPrice": "30.9", "BuyingQuantity": "3,000", "SellingPrice": "32.45",
       "SellingQuantity": "3000", "Highest": "33.1", "Lowest": "30.9", "Average": "31.43", "LatestPrice": "32.45",
       "Buy/Sell": "B", "SuspendTime": "000000", "TransactionVolume": "130469", "ApplyingDate": "", "ApplyingStatus": ""}


def test_a_row_is_normalized_with_a_real_trading_date_and_numeric_fields():
    [doc] = emerging.parse([ROW], datetime(2026, 10, 11, 18, 10))

    assert doc == {"stock_id": "1260", "date": datetime(2026, 10, 8), "name": "富味鄉", "last_price": 32.45,
                   "avg_price": 31.43, "prev_avg_price": 31.7, "high": 33.1, "low": 30.9, "volume": 130469,
                   "bid_price": 30.9, "bid_qty": 3000, "ask_price": 32.45, "ask_qty": 3000,
                   "data_source": "TPEX_ESB", "updated_at": datetime(2026, 10, 11, 18, 10)}


def test_blank_or_dash_prices_become_none_instead_of_zero():
    row = {**ROW, "Highest": "", "Lowest": "--", "LatestPrice": "", "TransactionVolume": ""}

    [doc] = emerging.parse([row], datetime(2026, 10, 11))

    assert doc["high"] is None and doc["low"] is None and doc["last_price"] is None and doc["volume"] is None


def test_rows_without_a_code_or_a_valid_roc_date_are_dropped():
    rows = [{**ROW, "SecuritiesCompanyCode": ""}, {**ROW, "Date": "bad"}, {**ROW, "Date": ""}]

    assert emerging.parse(rows, datetime(2026, 10, 11)) == []


def test_a_batch_mixing_two_dates_is_kept_row_by_row():
    rows = [ROW, {**ROW, "SecuritiesCompanyCode": "1269", "Date": "1151007"}]

    docs = emerging.parse(rows, datetime(2026, 10, 11))

    assert [d["date"] for d in docs] == [datetime(2026, 10, 8), datetime(2026, 10, 7)]


class Collection:
    def __init__(self):
        self.ops = []

    def bulk_write(self, ops, ordered=False):
        self.ops.extend(ops)

        class Result:
            upserted_count = len(ops)
            modified_count = 0

        return Result()


def test_upsert_is_keyed_by_stock_and_date_so_reruns_are_idempotent():
    docs = emerging.parse([ROW], datetime(2026, 10, 11))
    collection = Collection()

    emerging.upsert(collection, docs)

    op = collection.ops[0]
    assert op._filter == {"stock_id": "1260", "date": datetime(2026, 10, 8)}
    assert op._upsert is True and op._doc["$set"]["last_price"] == 32.45


def test_an_empty_response_is_not_written():
    collection = Collection()

    assert emerging.upsert(collection, []) is None and collection.ops == []
