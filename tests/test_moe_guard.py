"""MoE 守門：確保『分析失敗』的角色報告不進入顧問整合／合議投票。

對應 Phase 0-C。守門契約集中於 src/moe/guard.py，取代原本散落在
scripts/team_daily_verified.py 的 usable_reports()（腳本區域函式，team_analyze 無法共用）。
"""
import pytest

from src.moe.guard import (FAIL_PREFIX, is_failed_report, partition_reports,
                           usable_reports)


@pytest.mark.unit
def test_is_failed_report_detects_error_string():
    assert is_failed_report(f"{FAIL_PREFIX}: HTTPConnectionPool(host='172.16.9.27'...)")
    assert is_failed_report("整合失敗: timeout")
    assert not is_failed_report("技術面偏多，建議進場價 120，停損 110。")
    assert not is_failed_report("")
    assert not is_failed_report(None)  # 非字串視為非失敗（由上游決定）


@pytest.mark.unit
def test_usable_reports_excludes_failed_role():
    """失敗回應不得計入整合——這是決策正確性的守門契約。"""
    reports = {
        "technical-analyst": "分析失敗: server busy",
        "fundamental-analyst": "ROE 18%，毛利率穩定，財務健康。",
        "risk-manager": "整合失敗: connection reset",
    }
    assert usable_reports(reports) == {
        "fundamental-analyst": "ROE 18%，毛利率穩定，財務健康。"
    }


@pytest.mark.unit
def test_usable_reports_all_failed_returns_empty():
    reports = {"a": "分析失敗: x", "b": "分析失敗: y"}
    assert usable_reports(reports) == {}


@pytest.mark.unit
def test_usable_reports_handles_empty_or_none():
    assert usable_reports({}) == {}
    assert usable_reports(None) == {}


@pytest.mark.unit
def test_partition_reports_returns_ok_and_failed_roles():
    reports = {
        "technical-analyst": "分析失敗: 503",
        "value-analyst": "合理價 150，現價 120，低估。",
    }
    ok, failed = partition_reports(reports)
    assert ok == {"value-analyst": "合理價 150，現價 120，低估。"}
    assert failed == ["technical-analyst"]


@pytest.mark.unit
def test_failed_report_never_reaches_advisor_integration():
    """端到端契約：模擬呼叫端行為——只有 usable_reports 的內容能進整合輸入。"""
    reports = {"r1": "分析失敗: err", "r2": "正常報告"}
    advisor_input = usable_reports(reports)
    assert all(not v.startswith(FAIL_PREFIX) for v in advisor_input.values())
    assert "r1" not in advisor_input
