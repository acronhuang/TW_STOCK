"""TDD: 停機日補算的合理價欄位（綜合價，股價用當日收盤）。"""

import pytest

from src.data_gap import fair_value

pytestmark = pytest.mark.unit


def test_fields_carry_the_fair_value_the_margin_of_safety_and_the_source_tag():
    assert fair_value.fields(120.0, 100.0) == {"fair_value": 120.0, "margin_of_safety": 20.0,
                                               "fair_value_source": "composite_asof_price"}


def test_values_are_rounded_to_two_decimals():
    out = fair_value.fields(123.456, 99.99)

    assert out["fair_value"] == 123.46 and out["margin_of_safety"] == 23.47


def test_a_non_positive_or_missing_fair_value_writes_nothing():
    assert fair_value.fields(None, 100.0) is None
    assert fair_value.fields(0, 100.0) is None
    assert fair_value.fields(-5.0, 100.0) is None


def test_without_a_usable_price_only_the_fair_value_is_written():
    assert fair_value.fields(120.0, None) == {"fair_value": 120.0, "fair_value_source": "composite_asof_price"}
    assert fair_value.fields(120.0, 0) == {"fair_value": 120.0, "fair_value_source": "composite_asof_price"}


def test_the_earlier_dcf_ddm_only_marker_stays_replaceable_so_a_rerun_overwrites_it():
    assert "pit_dcf_ddm" in fair_value.REPLACEABLE and fair_value.SOURCE in fair_value.REPLACEABLE
