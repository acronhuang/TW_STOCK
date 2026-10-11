"""TDD: 按日期回補官方 PE/PB/殖利率（TWSE BWIBBU_d、TPEX peQryDate）。"""

from datetime import datetime

import pytest

from src.data_gap import valuation

pytestmark = pytest.mark.unit

DAY = datetime(2026, 9, 15)


def test_twse_rows_are_normalized_to_the_existing_stock_factors_fields():
    payload = {"stat": "OK", "data": [
        ["1101", "台泥", "23.80", "3.36", 114, "-", "0.77", "115/2"],
        ["1102", "亞泥", "35.20", "6.53", 114, "9.72", "0.68", "115/2"],
        ["2330", "台積電", "2,385.00", "0.92", 114, "1,234.50", "9.61", "115/2"],
    ]}

    rows = valuation.parse_twse(payload, DAY)

    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["1101"]["pe_ratio"] is None and by_symbol["1101"]["pb_ratio"] == 0.77
    assert by_symbol["1102"] == {"symbol": "1102", "date": DAY, "pe_ratio": 9.72, "pb_ratio": 0.68,
                                 "dividend_yield": 6.53, "data_source": "TWSE_BWIBBU"}
    assert by_symbol["2330"]["pe_ratio"] == 1234.5


def test_twse_zero_dividend_yield_is_stored_as_missing_like_the_daily_openapi_path():
    payload = {"stat": "OK", "data": [["1213", "大飲", "7.19", "0.00", 114, "-", "0.64", "115/2"]]}

    assert valuation.parse_twse(payload, DAY)[0]["dividend_yield"] is None


def test_a_non_ok_or_empty_twse_response_means_no_rows():
    assert valuation.parse_twse({"stat": "很抱歉，沒有符合條件的資料!"}, DAY) == []
    assert valuation.parse_twse({"stat": "OK", "data": []}, DAY) == []


def test_tpex_rows_keep_dividend_per_share_and_skip_non_numeric_codes():
    payload = {"stat": "ok", "tables": [{"data": [
        ["1240", "茂生農經        ", "10.26", "0.50000000", 114, "0.91", "1.63", "115Q2"],
        ["00679B", "元大美債20年", "--", "--", "", "--", "--", ""],
        ["1259", "安心            ", "--", "1.20000000", 114, "1.85", "0.75", "115Q2"],
    ]}]}

    rows = valuation.parse_tpex(payload, DAY)

    assert [r["symbol"] for r in rows] == ["1240", "1259"]
    assert rows[0] == {"symbol": "1240", "date": DAY, "pe_ratio": 10.26, "pb_ratio": 1.63, "dividend_yield": 0.91,
                       "dividend_per_share": 0.5, "data_source": "TPEX_PERATIO"}
    assert rows[1]["pe_ratio"] is None


def test_an_empty_tpex_table_means_no_rows():
    assert valuation.parse_tpex({"stat": "ok", "tables": [{"data": []}]}, DAY) == []
    assert valuation.parse_tpex({"stat": "ok", "tables": []}, DAY) == []


class Collection:
    def __init__(self):
        self.ops = []

    def bulk_write(self, ops, ordered=False):
        self.ops.extend(ops)

        class Result:
            upserted_count = len(ops)
            modified_count = 0

        return Result()


def test_writes_only_the_official_only_fields_and_never_pe_pb_which_the_nightly_job_owns():
    rows = [{"symbol": "1102", "date": DAY, "pe_ratio": 9.72, "pb_ratio": 0.68, "dividend_yield": 6.53,
             "data_source": "TWSE_BWIBBU"},
            {"symbol": "1240", "date": DAY, "pe_ratio": 10.26, "pb_ratio": 1.63, "dividend_yield": 0.91,
             "dividend_per_share": 0.5, "data_source": "TPEX_PERATIO"},
            {"symbol": "1101", "date": DAY, "pe_ratio": None, "pb_ratio": 0.77, "dividend_yield": None,
             "data_source": "TWSE_BWIBBU"}]
    collection = Collection()

    valuation.upsert(collection, rows, datetime(2026, 10, 11))

    sets = [op._doc["$set"] for op in collection.ops]
    assert sets[0] == {"dividend_yield": 6.53, "data_source": "TWSE_BWIBBU", "updated_at": datetime(2026, 10, 11)}
    assert sets[1]["dividend_per_share"] == 0.5 and sets[1]["dividend_yield"] == 0.91
    assert all("pe_ratio" not in s and "pb_ratio" not in s for s in sets)
    assert sets[2] == {"data_source": "TWSE_BWIBBU", "updated_at": datetime(2026, 10, 11)}
    assert all(op._filter == {"symbol": op._filter["symbol"], "date": DAY} for op in collection.ops)


def test_official_values_are_never_overwritten_by_derived_ones_only_filled_in():
    assert valuation.OFFICIAL_SOURCES == {"TWSE_BWIBBU", "TPEX_PERATIO"}


def _counts(days, twse=860, tpex=670):
    return {d: {"TWSE_BWIBBU": twse, "TPEX_PERATIO": tpex, None: 600} for d in days}


CAL = [f"202609{d:02d}" for d in (1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24)]


def test_a_day_missing_one_official_source_is_detected_even_when_the_other_is_fine():
    counts = _counts(CAL)
    counts["20260914"]["TWSE_BWIBBU"] = 0

    gaps = valuation.thin_days(counts, CAL)

    assert [(d, s) for d, s, _, _ in gaps] == [("20260914", "TWSE_BWIBBU")]


def test_a_day_with_no_official_rows_at_all_is_detected_for_both_sources():
    counts = _counts(CAL)
    counts["20260915"] = {None: 1500}

    gaps = valuation.thin_days(counts, CAL)

    assert {(d, s) for d, s, _, _ in gaps} == {("20260915", "TWSE_BWIBBU"), ("20260915", "TPEX_PERATIO")}


def test_normal_days_and_small_natural_variation_are_not_gaps():
    counts = _counts(CAL)
    counts["20260916"]["TWSE_BWIBBU"] = 845

    assert valuation.thin_days(counts, CAL) == []


def test_too_few_neighbours_means_no_judgement_instead_of_a_false_alarm():
    assert valuation.thin_days({"20260901": {"TWSE_BWIBBU": 0}}, ["20260901"]) == []


def test_the_policy_backfills_the_valuation_gap_by_date():
    from src.data_gap import policy

    recovery = policy.recovery_for("stock_factors_valuation", "20260915")

    assert recovery.mode == "backfill"
    assert ("backfill_valuation_by_date.py", "--date", "20260915", "--apply") in recovery.commands
