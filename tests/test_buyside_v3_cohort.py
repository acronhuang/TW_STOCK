"""TDD:v3.1 群體相對純品質(買進群內 ROE 底四分位降級)。mongomock → @unit。"""
import pytest
mongomock = pytest.importorskip("mongomock")
pytest.importorskip("numpy")
from src.analysis.buyside.shadow_writer import run_shadow_cohort_quality
from src.analysis.buyside.backtest_compare import compare


@pytest.mark.unit
def test_cohort_downgrades_bottom_quartile_and_improves():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    # 8 檔買進,ROE 1..8;底四分位(<=~2.75)= ROE 1,2 兩檔(輸家)
    docs, facs = [], []
    for i, roe in enumerate([1, 2, 3, 4, 5, 6, 7, 8], 1):
        loser = roe <= 2
        docs.append({"symbol": f"S{i}", "window": 20, "verdict": "買進",
                     "hit": (not loser), "excess": (-0.05 if loser else 0.04)})
        facs.append({"symbol": f"S{i}", "date": "2026-09-20", "roe": float(roe)})
    db["verdict_detail"].insert_many(docs)
    db["stock_factors"].insert_many(facs)
    res = run_shadow_cohort_quality(db, window=20, field="buy_v3c", pctile_lo=25.0)
    assert res["n"] == 8 and res["downgraded"] == 2      # 底四分位 2 檔
    cmp = compare(db, window=20, field="buy_v3c")
    assert cmp["v2"]["hit_rate"] > cmp["v1"]["hit_rate"]  # 移除輸家 → 命中↑
    assert cmp["v2"]["mean_excess"] > cmp["v1"]["mean_excess"]
