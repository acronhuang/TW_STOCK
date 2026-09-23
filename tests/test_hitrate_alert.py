"""命中率連續下滑 / 跌破地板告警判定測試。"""
import pytest

from src.audit.verdict_tracker import build_hitrate_alert, count_trailing_drops


@pytest.mark.unit
def test_count_trailing_drops_counts_tail_strict_decreases():
    # 0.5→0.6(升,停) | 0.6→0.55(跌) | 0.55→0.5(跌) → 尾端連跌 2
    assert count_trailing_drops([0.5, 0.6, 0.55, 0.5]) == 2
    assert count_trailing_drops([0.4, 0.4, 0.4]) == 0        # 持平非下滑
    assert count_trailing_drops([0.7]) == 0
    assert count_trailing_drops([]) == 0


@pytest.mark.unit
def test_consecutive_drops_trigger_alert():
    series = [(i, v) for i, v in enumerate([0.7, 0.65, 0.6, 0.55])]  # 連跌 3
    a = build_hitrate_alert(series, max_consecutive_drops=3)
    assert a is not None
    assert a["level"] == "warning"
    assert a["detail"]["consecutive_drops"] == 3


@pytest.mark.unit
def test_floor_breach_triggers_alert():
    series = [(1, 0.6), (2, 0.62), (3, 0.35)]  # 升升但最新跌破地板 0.4
    a = build_hitrate_alert(series, max_consecutive_drops=3, floor=0.4)
    assert a is not None
    assert a["detail"]["latest"] == 0.35


@pytest.mark.unit
def test_stable_series_no_alert():
    series = [(i, v) for i, v in enumerate([0.6, 0.62, 0.61, 0.63])]
    assert build_hitrate_alert(series, max_consecutive_drops=3, floor=0.4) is None
