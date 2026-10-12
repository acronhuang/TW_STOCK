"""TDD: 上櫃回補的成交量要含零股與盤後（與 FinMind／TPEX dailyQuotes 一致），不可只用整股盤的張數。"""

from bson.decimal128 import Decimal128

import pytest

from scripts import backfill_by_date as bbd

pytestmark = pytest.mark.unit


def payload(rows, stat="ok", date="20260917"):
    fields = ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價", " 成交股數", "成交金額(元)", "成交筆數"]
    return {"stat": stat, "date": date, "tables": [{"fields": fields, "data": rows}]}


def row(code, shares, amount, trades):
    return [code, "名", "10", "0", "10", "10", "10", "10", shares, amount, trades]


def test_totals_are_read_by_header_so_a_shifted_column_cannot_be_mistaken_for_volume():
    totals = bbd.parse_tpex_totals(payload([row("6884", "2,589", "78,801", "5")]), "20260917")

    assert totals == {"6884": {"volume": 2589.0, "amount": "78801", "transaction": "5"}}


def test_a_failed_status_or_a_different_day_gives_no_totals():
    assert bbd.parse_tpex_totals(payload([row("6884", "1", "1", "1")], stat="error"), "20260917") == {}
    assert bbd.parse_tpex_totals(payload([row("6884", "1", "1", "1")], date="20260916"), "20260917") == {}


def test_apply_totals_overlays_volume_amount_and_transaction_only_for_known_codes():
    recs = [{"stock_id": "6884", "volume": Decimal128("2000"), "amount": "61000", "transaction": "2"},
            {"stock_id": "9999", "volume": Decimal128("5000"), "amount": "1", "transaction": "1"}]

    out = bbd.apply_totals(recs, {"6884": {"volume": 2589.0, "amount": "78801", "transaction": "5"}})

    assert out[0]["volume"] == Decimal128("2589.0") and out[0]["amount"] == "78801" and out[0]["transaction"] == "5"
    assert out[1]["volume"] == Decimal128("5000") and out[1]["amount"] == "1"


def test_refresh_plan_only_touches_otc_rows_whose_numbers_actually_differ():
    docs = [{"stock_id": "6884", "volume": Decimal128("2000"), "amount": "61000", "transaction": "2"},
            {"stock_id": "1586", "volume": Decimal128("208779"), "amount": "3736668", "transaction": "185"},
            {"stock_id": "7777", "volume": Decimal128("1"), "amount": "1", "transaction": "1"}]
    totals = {"6884": {"volume": 2589.0, "amount": "78801", "transaction": "5"},
              "1586": {"volume": 208779.0, "amount": "3736668", "transaction": "185"}}

    plan = bbd.refresh_plan(docs, totals)

    assert [stock for stock, _ in plan] == ["6884"]
    assert plan[0][1] == {"volume": Decimal128("2589.0"), "amount": "78801", "transaction": "5"}
