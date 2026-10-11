"""TDD: 券資比（融券餘額 / 融資餘額）寫入 stock_factors。"""

from datetime import datetime

import pytest

from src.chip_analysis import margin_ratio

pytestmark = pytest.mark.unit

DAY = datetime(2026, 10, 9)


def test_ratio_is_short_balance_over_margin_balance_in_percent():
    assert margin_ratio.short_margin_ratio(12383, 2) == 0.02
    assert margin_ratio.short_margin_ratio(1000, 250) == 25.0


def test_no_margin_balance_or_missing_values_have_no_ratio():
    assert margin_ratio.short_margin_ratio(0, 5) is None
    assert margin_ratio.short_margin_ratio(None, 5) is None
    assert margin_ratio.short_margin_ratio(1000, None) is None


def test_decimal128_and_numeric_strings_from_mongo_are_accepted():
    from bson.decimal128 import Decimal128

    assert margin_ratio.short_margin_ratio(Decimal128("2000"), Decimal128("500")) == 25.0
    assert margin_ratio.short_margin_ratio("2,000", "500") == 25.0


class Collection:
    def __init__(self):
        self.ops = []

    def bulk_write(self, ops, ordered=False):
        self.ops.extend(ops)

        class Result:
            matched_count = len(ops)
            modified_count = len(ops)

        return Result()


def test_only_the_ratio_field_is_written_and_never_creates_new_factor_documents():
    docs = [{"code": "2330", "margin_balance": 1000, "short_balance": 250},
            {"code": "1101", "margin_balance": 0, "short_balance": 3}]
    collection = Collection()

    margin_ratio.apply_day(collection, DAY, docs)

    set_op, unset_op = collection.ops
    assert set_op._filter == {"symbol": "2330", "date": DAY}
    assert set_op._doc == {"$set": {"short_margin_ratio": 25.0}}
    assert set_op._upsert is False
    assert unset_op._doc == {"$unset": {"short_margin_ratio": ""}}


def test_rows_without_a_code_are_skipped_and_rows_without_balances_clear_a_stale_ratio():
    collection = Collection()

    margin_ratio.apply_day(collection, DAY, [{"code": "9999"}, {"code": ""}])

    assert len(collection.ops) == 1
    assert collection.ops[0]._filter == {"symbol": "9999", "date": DAY}
    assert collection.ops[0]._doc == {"$unset": {"short_margin_ratio": ""}}
