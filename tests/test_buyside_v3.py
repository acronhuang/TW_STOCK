"""TDD:v3 純品質(ROE)tilt。roe_pctile 特徵 + rescore_v3 + shadow/compare 參數化。"""
import pytest

mongomock = pytest.importorskip("mongomock")

from src.analysis.buyside.features import extract_buy_features
from src.analysis.buyside.buy_rescore import rescore_v3
from src.analysis.buyside.shadow_writer import run_shadow
from src.analysis.buyside.backtest_compare import compare


@pytest.mark.unit
def test_features_roe_pctile():
    uni = {"pe": [10, 20, 30], "pb": [1, 2, 3], "roe": [5, 10, 15, 20]}
    f = extract_buy_features({"prior_20d": 0.0, "pe": 20.0, "pb": 2.0, "roe": 5.0}, uni)
    assert f["roe_pctile"] == pytest.approx(0.0)          # 最低 ROE → 0 百分位
    f2 = extract_buy_features({"pe": 20.0, "pb": 2.0, "roe": 20.0}, uni)
    assert f2["roe_pctile"] == pytest.approx(75.0)


def _f(roe_pctile=50.0, coverage_ok=True):
    return {"prior_20d": 0.09, "pe_pctile": 90, "pb_pctile": 90,
            "roe": 10.0, "roe_pctile": roe_pctile, "coverage_ok": coverage_ok}


@pytest.mark.unit
def test_rescore_v3_low_quality_downgrades():
    assert rescore_v3(_f(roe_pctile=10))["v2"] == "降級持有"    # 底四分位品質 → 降級


@pytest.mark.unit
def test_rescore_v3_high_quality_keeps_buy():
    assert rescore_v3(_f(roe_pctile=80))["v2"] == "買進"


@pytest.mark.unit
def test_rescore_v3_guards():
    assert rescore_v3(_f(coverage_ok=False, roe_pctile=1))["v2"] == "買進"   # 特徵不足→維持
    assert rescore_v3({"coverage_ok": True, "roe_pctile": None})["v2"] == "買進"  # 無法排名→維持


@pytest.mark.unit
def test_shadow_v3_field_and_compare():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    db["verdict_detail"].insert_many([
        {"symbol": "L", "window": 20, "verdict": "買進", "hit": False, "excess": -0.08},  # 低品質輸家
        {"symbol": "H", "window": 20, "verdict": "買進", "hit": True, "excess": 0.05},
    ])
    db["stock_factors"].insert_many([
        {"symbol": "L", "date": "2026-09-20", "pe_ratio": 20, "pb_ratio": 2, "roe": 2.0},
        {"symbol": "H", "date": "2026-09-20", "pe_ratio": 20, "pb_ratio": 2, "roe": 25.0},
    ])
    n = run_shadow(db, window=20, scorer=rescore_v3, field="buy_v3")
    assert n == 2
    assert db["verdict_detail"].find_one({"symbol": "L"})["buy_v3"] == "降級持有"
    assert db["verdict_detail"].find_one({"symbol": "H"})["buy_v3"] == "買進"
    res = compare(db, window=20, field="buy_v3")
    assert res["downgraded"] == 1
    assert res["v2"]["hit_rate"] > res["v1"]["hit_rate"]   # 移除低品質輸家 → 命中↑
