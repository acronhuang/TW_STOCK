"""TDD:eval_v5_shadow — 接 advisor_v5_rating→verdict_detail 超額,比較 live vs v5。@unit。"""
import pytest
mongomock = pytest.importorskip("mongomock")
from src.analysis.buyside.backtest_compare import eval_v5_shadow


@pytest.mark.unit
def test_eval_v5_joins_and_compares():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    # L=v5降級的輸家, K=v5保留的贏家(皆多頭)
    db["team_analysis"].insert_many([
        {"symbol": "L", "date": "2026-08-01", "advisor_v5_rating": "觀望", "advisor_v5_regime": "多頭"},
        {"symbol": "K", "date": "2026-08-01", "advisor_v5_rating": "買進", "advisor_v5_regime": "多頭"},
    ])
    db["verdict_detail"].insert_many([
        {"symbol": "L", "date": "2026-08-01", "window": 20, "verdict": "買進", "hit": False, "excess": -0.06},
        {"symbol": "K", "date": "2026-08-01", "window": 20, "verdict": "買進", "hit": True, "excess": 0.05},
    ])
    r = eval_v5_shadow(db, window=20)
    o = r["overall"]
    assert o["live"]["n"] == 2 and o["v5"]["n"] == 1 and o["downgraded"] == 1
    assert o["v5"]["hit_rate"] > o["live"]["hit_rate"]       # 移除輸家 L → v5 命中↑
    assert o["v5"]["mean_excess"] > o["live"]["mean_excess"]
    assert "多頭" in r and r["多頭"]["downgraded"] == 1

@pytest.mark.unit
def test_eval_v5_date_window_oos():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    db["team_analysis"].insert_one({"symbol": "A", "date": "2026-08-20", "advisor_v5_rating": "觀望", "advisor_v5_regime": "多頭"})
    db["verdict_detail"].insert_one({"symbol": "A", "date": "2026-08-20", "window": 20, "verdict": "買進", "hit": False, "excess": -0.05})
    assert eval_v5_shadow(db, date_hi="2026-08-15")["overall"]["live"]["n"] == 0   # 切在 08-15 前→排除
    assert eval_v5_shadow(db, date_lo="2026-08-15")["overall"]["live"]["n"] == 1
