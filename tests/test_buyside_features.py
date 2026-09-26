"""TDD(red→green):M1 買方特徵萃取器。純函式,免 DB → @unit。

驗收(對應 docs/plans/verdict_buyside_v1.md M1):
- pctile_rank 正確計算百分位
- extract_buy_features 缺 PE/ROE → coverage_ok=False 且不拋錯
"""
import pytest

from src.analysis.buyside.features import pctile_rank, extract_buy_features


@pytest.mark.unit
def test_pctile_rank_basic():
    uni = [10, 20, 30, 40, 50]
    assert pctile_rank(10, uni) == pytest.approx(0.0, abs=1e-6)
    assert pctile_rank(50, uni) == pytest.approx(80.0, abs=1e-6)   # searchsorted/len*100
    assert pctile_rank(30, uni) == pytest.approx(40.0, abs=1e-6)


@pytest.mark.unit
def test_pctile_rank_empty_returns_none():
    assert pctile_rank(10, []) is None


@pytest.mark.unit
def test_extract_features_full_coverage():
    rec = {"prior_20d": 0.06, "pe": 25.0, "pb": 4.0, "roe": 15.0}
    uni = {"pe": [10, 15, 20, 25, 30], "pb": [1, 2, 3, 4, 5]}
    f = extract_buy_features(rec, uni)
    assert f["coverage_ok"] is True
    assert f["prior_20d"] == 0.06
    assert 0 <= f["pe_pctile"] <= 100
    assert f["roe"] == 15.0


@pytest.mark.unit
def test_extract_features_missing_pe_or_roe_marks_incomplete():
    uni = {"pe": [10, 20, 30], "pb": [1, 2, 3]}
    assert extract_buy_features({"prior_20d": 0.02, "pe": None, "roe": 12.0}, uni)["coverage_ok"] is False
    assert extract_buy_features({"prior_20d": 0.02, "pe": 20.0, "roe": None}, uni)["coverage_ok"] is False
    # 缺值不得拋錯
    extract_buy_features({}, uni)
