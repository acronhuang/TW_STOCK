"""TDD:buyside_validate_v5.gonogo — Go/No-Go 判定(純讀取,mongomock)。@unit。"""
import pytest
mongomock = pytest.importorskip("mongomock")
from scripts.buyside_validate_v5 import gonogo


def _mk(pairs):
    """pairs: [(symbol,date,rating,regime,excess,hit)] → 建 team_analysis+verdict_detail。"""
    db = mongomock.MongoClient()["tw_stock_analysis"]
    ta, vd = [], []
    for s, d, rat, reg, ex, hit in pairs:
        ta.append({"symbol": s, "date": d, "advisor_v5_rating": rat, "advisor_v5_regime": reg})
        vd.append({"symbol": s, "date": d, "window": 20, "verdict": "買進", "excess": ex, "hit": hit})
    db["team_analysis"].insert_many(ta); db["verdict_detail"].insert_many(vd)
    return db


@pytest.mark.unit
def test_gonogo_pass_when_v5_improves_both_segments():
    # 前段(07月)與後段(08月)v5 都移除輸家(觀望)、保留贏家(買進)
    pairs = []
    for mon in ("2026-07", "2026-08"):
        pairs += [(f"L{mon}", f"{mon}-05", "觀望", "多頭", -0.06, False),
                  (f"K{mon}", f"{mon}-06", "買進", "多頭", 0.05, True)] * 40  # 撐樣本
    db = _mk(pairs)
    crit, passed = gonogo(db, split_date="2026-08-01", min_n=50)
    assert passed is True
    assert crit["① 整體 v5>live(命中+超額)"][0] is True
    assert crit["② 前後段皆超額改善(OOS 一致)"][0] is True


@pytest.mark.unit
def test_gonogo_fail_when_no_improvement():
    # v5 全保留買進(沒移除輸家)→ v5==live → 不改善 → NO-GO
    pairs = [(f"A{i}", "2026-08-05", "買進", "多頭", (-0.05 if i % 2 else 0.03), bool(i % 2)) for i in range(120)]
    db = _mk(pairs)
    crit, passed = gonogo(db, split_date="2026-08-01", min_n=50)
    assert passed is False
    assert crit["① 整體 v5>live(命中+超額)"][0] is False
