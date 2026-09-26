"""TDD:v4 regime-aware。classify_regime(大盤趨勢)+ run_shadow_regime_aware
(只在趨勢市套品質 tilt,盤整維持)。mongomock → @unit。"""
from datetime import datetime, timedelta

import pytest

mongomock = pytest.importorskip("mongomock")
pytest.importorskip("numpy")

from src.analysis.buyside.regime import classify_regime
from src.analysis.buyside.shadow_writer import run_shadow_regime_aware
from src.analysis.buyside.backtest_compare import compare


def _seed_taiex(db, start_close, end_close, asof):
    """21 個交易日 TAIEX,由 start→end 線性。"""
    docs = []
    for i in range(21):
        c = start_close + (end_close - start_close) * i / 20
        docs.append({"symbol": "TAIEX", "date": asof - timedelta(days=20 - i), "close": round(c, 2)})
    db["stock_price"].insert_many(docs)


@pytest.mark.unit
def test_classify_regime_bull_flat_bear():
    asof = datetime(2026, 8, 20)
    db = mongomock.MongoClient()["t1"]; _seed_taiex(db, 100, 110, asof)   # +10%
    assert classify_regime(db, asof) == "多頭"
    db2 = mongomock.MongoClient()["t2"]; _seed_taiex(db2, 100, 100.5, asof)  # ~0%
    assert classify_regime(db2, asof) == "盤整"
    db3 = mongomock.MongoClient()["t3"]; _seed_taiex(db3, 100, 90, asof)   # -10%
    assert classify_regime(db3, asof) == "空頭"


@pytest.mark.unit
def test_regime_aware_only_tilts_trending():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    # 兩檔低品質買進:T 在趨勢日、R 在盤整日。regime_fn 注入(免鋪 TAIEX)
    db["verdict_detail"].insert_many([
        {"symbol": "T", "date": "2026-08-01", "window": 20, "verdict": "買進", "hit": False, "excess": -0.05},
        {"symbol": "R", "date": "2026-08-15", "window": 20, "verdict": "買進", "hit": False, "excess": -0.05},
        {"symbol": "TH", "date": "2026-08-01", "window": 20, "verdict": "買進", "hit": True, "excess": 0.04},
    ])
    db["stock_factors"].insert_many([
        {"symbol": "T", "date": "2026-08-01", "roe": 1.0},    # 低品質
        {"symbol": "R", "date": "2026-08-15", "roe": 1.0},    # 低品質(但盤整→不動)
        {"symbol": "TH", "date": "2026-08-01", "roe": 25.0},  # 高品質
    ])
    regime_fn = lambda dt: "多頭" if str(dt)[:10] == "2026-08-01" else "盤整"
    res = run_shadow_regime_aware(db, window=20, field="buy_v4", regime_fn=regime_fn)
    assert db["verdict_detail"].find_one({"symbol": "T"})["buy_v4"] == "降級持有"   # 趨勢+低品質→降
    assert db["verdict_detail"].find_one({"symbol": "R"})["buy_v4"] == "買進"       # 盤整→維持(不動)
    assert db["verdict_detail"].find_one({"symbol": "TH"})["buy_v4"] == "買進"      # 高品質→維持
    assert res["downgraded"] == 1
