"""AI verdict 品質回饋迴路測試 —— 事後歸因(命中率/校準)。"""
import pytest

from src.audit.verdict_tracker import (compute_metrics, evaluate_verdict,
                                       forward_return, is_hit)


@pytest.mark.unit
def test_forward_return():
    assert forward_return(100, 110) == pytest.approx(0.10)
    assert forward_return(100, 90) == pytest.approx(-0.10)
    assert forward_return(0, 100) is None      # 無效進場價


@pytest.mark.unit
def test_is_hit_buy_sell_hold():
    # 買進：漲超過 band 才算命中
    assert is_hit("買進", 0.05) is True
    assert is_hit("買進", 0.01) is False
    # 賣出：跌超過 band 才算命中
    assert is_hit("賣出", -0.05) is True
    assert is_hit("賣出", 0.05) is False
    # 持有：在 band 內算命中（沒大波動）
    assert is_hit("持有", 0.01) is True
    assert is_hit("持有", 0.08) is False


@pytest.mark.unit
def test_evaluate_verdict():
    r = evaluate_verdict({"symbol": "2330", "verdict": "買進", "entry_price": 100},
                         later_price=115)
    assert r["symbol"] == "2330"
    assert r["ret"] == pytest.approx(0.15)
    assert r["hit"] is True


@pytest.mark.unit
def test_evaluate_verdict_skips_invalid():
    assert evaluate_verdict({"symbol": "X", "verdict": "買進", "entry_price": None},
                            later_price=100) is None


@pytest.mark.unit
def test_compute_metrics_overall_and_by_verdict():
    evaluated = [
        {"verdict": "買進", "hit": True}, {"verdict": "買進", "hit": False},
        {"verdict": "買進", "hit": True}, {"verdict": "賣出", "hit": True},
        {"verdict": "持有", "hit": False},
    ]
    m = compute_metrics(evaluated)
    assert m["n"] == 5
    assert m["hit_rate"] == pytest.approx(3 / 5)
    assert m["by_verdict"]["買進"]["n"] == 3
    assert m["by_verdict"]["買進"]["hit_rate"] == pytest.approx(2 / 3)
    assert m["by_verdict"]["賣出"]["hit_rate"] == pytest.approx(1.0)


@pytest.mark.unit
def test_compute_metrics_empty():
    m = compute_metrics([])
    assert m["n"] == 0 and m["hit_rate"] is None


@pytest.mark.unit
def test_normalize_verdict():
    from src.audit.verdict_tracker import normalize_verdict
    assert normalize_verdict("強力買進") == "買進"
    assert normalize_verdict("減碼") == "賣出"
    assert normalize_verdict("觀望") == "持有"
    assert normalize_verdict("未知") == "持有"


@pytest.mark.unit
def test_evaluate_verdict_maps_team_analysis_fields():
    """team_analysis 用 final_verdict / price_at_analysis → 應正確對應。"""
    r = evaluate_verdict({"symbol": "2330", "final_verdict": "強力買進",
                          "price_at_analysis": 100}, later_price=110)
    assert r["verdict"] == "買進" and r["ret"] == pytest.approx(0.10) and r["hit"] is True
