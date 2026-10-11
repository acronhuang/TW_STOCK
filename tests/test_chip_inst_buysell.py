"""TDD: 三大法人買進／賣出分列（原本只存買賣超淨額）。"""

import pytest
from bson.decimal128 import Decimal128

from src.chip_analysis import inst_buysell

pytestmark = pytest.mark.unit


def _f(doc):
    return {k: float(v.to_decimal()) for k, v in doc.items()}


def t86_row(**cells):
    row = ["2330", "台積電"] + ["0"] * 17
    for index, value in cells.items():
        row[int(index[1:])] = value
    return row


def test_twse_t86_foreign_is_investor_plus_foreign_dealer_matching_the_net_definition():
    row = t86_row(c2="1,000", c3="400", c4="600", c5="50", c6="20", c7="30")

    assert _f(inst_buysell.from_t86(row))["foreign_buy"] == 1050.0
    assert _f(inst_buysell.from_t86(row))["foreign_sell"] == 420.0


def test_twse_t86_dealer_is_self_plus_hedging_and_trust_is_its_own_block():
    row = t86_row(c8="700", c9="100", c10="600", c11="150",
                  c12="300", c13="250", c14="50", c15="200", c16="100", c17="100")

    out = _f(inst_buysell.from_t86(row))

    assert (out["trust_buy"], out["trust_sell"]) == (700.0, 100.0)
    assert (out["dealer_buy"], out["dealer_sell"]) == (500.0, 350.0)


def test_twse_t86_values_are_stored_as_decimal128_like_the_rest_of_institutional_flow():
    row = t86_row(c2="10", c3="4", c4="6")

    assert isinstance(inst_buysell.from_t86(row)["foreign_buy"], Decimal128)


def test_twse_t86_row_whose_buy_minus_sell_does_not_match_the_net_is_not_trusted():
    row = t86_row(c2="1,000", c3="400", c4="999")

    assert inst_buysell.from_t86(row) == {}


def test_twse_t86_short_rows_are_ignored():
    assert inst_buysell.from_t86(["2330", "台積電", "1"]) == {}


def tpex_open_row(**extra):
    row = {
        "ForeignInvestorsIncludeMainlandAreaInvestors-TotalBuy": "1,304,000",
        "ForeignInvestorsIncludeMainlandAreaInvestors-TotalSell": "1,619,500",
        "ForeignInvestorsInclude MainlandAreaInvestors-Difference": "-315,500",
        "SecuritiesInvestmentTrustCompanies-TotalBuy": "0",
        "SecuritiesInvestmentTrustCompanies-TotalSell": "0",
        "SecuritiesInvestmentTrustCompanies-Difference": "0",
        "Dealers-TotalBuy": "2851583",
        "Dealers-TotalSell": "6046351",
        "Dealers-Difference": "-3194768",
    }
    row.update(extra)
    return row


def test_tpex_openapi_row_maps_total_buy_and_total_sell_columns():
    out = _f(inst_buysell.from_tpex_openapi(tpex_open_row()))

    assert out == {"foreign_buy": 1304000.0, "foreign_sell": 1619500.0, "trust_buy": 0.0, "trust_sell": 0.0,
                   "dealer_buy": 2851583.0, "dealer_sell": 6046351.0}


def test_tpex_openapi_falls_back_to_the_misspelled_sell_column_the_api_also_emits():
    row = tpex_open_row()
    del row["Dealers-TotalSell"]
    row["Dealers -TotalSell"] = "6046351"

    assert _f(inst_buysell.from_tpex_openapi(row))["dealer_sell"] == 6046351.0


def test_tpex_openapi_row_failing_the_buy_sell_net_check_is_not_trusted():
    assert inst_buysell.from_tpex_openapi(tpex_open_row(**{"Dealers-Difference": "5"})) == {}


def test_tpex_dated_table_uses_the_triplet_positions_for_total_foreign_trust_and_dealer():
    row = ["6488", "環球晶"] + ["0"] * 22
    row[8], row[9], row[10] = "900", "400", "500"
    row[11], row[12], row[13] = "50", "20", "30"
    row[20], row[21], row[22] = "10", "70", "-60"

    out = _f(inst_buysell.from_tpex_dated(row))

    assert out == {"foreign_buy": 900.0, "foreign_sell": 400.0, "trust_buy": 50.0, "trust_sell": 20.0,
                   "dealer_buy": 10.0, "dealer_sell": 70.0}


def test_tpex_dated_row_with_shifted_columns_is_not_trusted():
    row = ["6488", "環球晶"] + ["0"] * 22
    row[8], row[9], row[10] = "900", "400", "7"

    assert inst_buysell.from_tpex_dated(row) == {}
