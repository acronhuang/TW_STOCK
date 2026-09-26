"""TDD:M3 影子寫入器 + M4 回測比較器。mongomock 免真 DB → @unit。

M3 驗收:只寫 buy_v2 shadow 欄,絕不動 verdict/final_verdict;--dry-run 不寫。
M4 驗收:v1(全買進)vs v2(未被降級的買進)命中/超額對照;降級掉輸家 → v2 命中↑。
"""
import pytest

mongomock = pytest.importorskip("mongomock")

from src.analysis.buyside.shadow_writer import run_shadow
from src.analysis.buyside.backtest_compare import compare


def _db():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    # 3 檔買進:A 追高+貴(該降級,且是輸家 hit=False)、B 追高+便宜高品質(維持)、C 低動能(維持)
    db["verdict_detail"].insert_many([
        {"symbol": "A", "date": "2026-09-20", "window": 20, "verdict": "買進",
         "prior_20d": 0.09, "hit": False, "excess": -0.05},
        {"symbol": "B", "date": "2026-09-20", "window": 20, "verdict": "買進",
         "prior_20d": 0.09, "hit": True, "excess": 0.04},
        {"symbol": "C", "date": "2026-09-20", "window": 20, "verdict": "買進",
         "prior_20d": 0.01, "hit": True, "excess": 0.03},
    ])
    db["stock_factors"].insert_many([
        {"symbol": "A", "date": "2026-09-20", "pe_ratio": 40.0, "pb_ratio": 6.0, "roe": 5.0},   # 貴+低品質
        {"symbol": "B", "date": "2026-09-20", "pe_ratio": 8.0, "pb_ratio": 1.0, "roe": 22.0},   # 便宜+高品質
        {"symbol": "C", "date": "2026-09-20", "pe_ratio": 15.0, "pb_ratio": 2.0, "roe": 15.0},
    ])
    return db


@pytest.mark.unit
def test_shadow_writes_buy_v2_only_not_live():
    db = _db()
    n = run_shadow(db, window=20)
    assert n == 3
    a = db["verdict_detail"].find_one({"symbol": "A"})
    assert a["buy_v2"] == "降級持有"          # 追高+貴/低品質 → 降級
    assert a["verdict"] == "買進"             # live 欄位位元不變
    assert "final_verdict" not in a or a.get("final_verdict") == a.get("final_verdict")
    assert db["verdict_detail"].find_one({"symbol": "B"})["buy_v2"] == "買進"
    assert db["verdict_detail"].find_one({"symbol": "C"})["buy_v2"] == "買進"


@pytest.mark.unit
def test_shadow_dry_run_writes_nothing():
    db = _db()
    run_shadow(db, window=20, dry_run=True)
    assert all("buy_v2" not in d for d in db["verdict_detail"].find({}))


@pytest.mark.unit
def test_compare_v2_beats_v1_when_downgrading_losers():
    db = _db()
    run_shadow(db, window=20)
    res = compare(db, window=20)
    assert res["v1"]["n"] == 3 and res["v2"]["n"] == 2      # A 被降級移出 v2 買進集
    assert res["downgraded"] == 1
    assert res["v2"]["hit_rate"] > res["v1"]["hit_rate"]    # 移除輸家 A → 命中率上升
    assert res["v2"]["mean_excess"] > res["v1"]["mean_excess"]
