"""Ollama↔規則 一致率跨門檻告警判定測試。"""
import pytest

from src.audit.ab_verdict import build_agreement_alert


@pytest.mark.unit
def test_below_threshold_returns_alert():
    a = build_agreement_alert(0.45, threshold=0.6, n=20, changed_count=11)
    assert a is not None
    assert a["level"] == "warning"
    assert "45.0%" in a["message"]
    assert a["detail"]["agreement_rate"] == 0.45
    assert a["detail"]["changed_count"] == 11


@pytest.mark.unit
def test_at_or_above_threshold_no_alert():
    assert build_agreement_alert(0.6, threshold=0.6) is None
    assert build_agreement_alert(0.9, threshold=0.6) is None


@pytest.mark.unit
def test_none_agreement_no_alert():
    """無共同標的（agreement_rate=None）不應誤觸告警。"""
    assert build_agreement_alert(None, threshold=0.6) is None
